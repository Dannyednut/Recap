from typing import Literal
from eth_account import Account
from eth_account.messages import encode_structured_data, encode_typed_data
from web3 import Web3
import time
import requests
import json
import os

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
ALCHEMY_API_KEY = os.getenv("ALCHEMY_API_KEY")
COMPROMISED_PRIVATE_KEY = os.getenv("COMPROMISED_PRIVATE_KEY")  # owner
CLEAN_PRIVATE_KEY = os.getenv("CLEAN_PRIVATE_KEY") 
DAI_ADDRESS = "0xFF34B3d4Aee8ddCd6F9AFFFB6Fe49bD371b8a357"
USDC_ADDRESS = "0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8"
TOKEN_PULLER_ADDRESS = os.getenv("TOKEN_PULLER_ADDRESS")

def fetch_abi_from_etherscan(contract_address, api_key = ETHERSCAN_API_KEY, network='sepolia'):
    url = 'https://api.etherscan.io/v2/api'
    chain_id = {
        'mainnet': 1,
        'goerli': 5,
        'sepolia': 11155111,
        'base': 8453,
        'basegoerli': 84531,
        'optimism': 10,
        'optimismgoerli': 420,
        'arbitrum': 42161,
        'arbitrumgoerli': 421613,
        'bsc': 56,
        'bscgoerli': 97,
        'polygon': 137,
        'polygongoerli': 899,
        'avalanche': 43114,
        'avalanchegoerli': 43113,
    }
    r = requests.get(url, params={
        'chainid': chain_id[network],
        'module': 'contract',
        'action': 'getabi',
        'address': contract_address,
        'apikey': api_key
    })
    data = r.json()
    return json.loads(data['result'])

def permit_token(w3: Web3, private_key: str, token_address: str, spender: str, max_approval: bool = True, expiry: int = None, network: str = 'sepolia'):
    acct = Account.from_key(private_key)
    owner = acct.address
    amount = 2**256 - 1 if max_approval else 100 * 10**18

    abi = fetch_abi_from_etherscan(token_address, network=network)

    token = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=abi)

    # Inspect permit signature to detect style
    permit_abi = token.get_function_by_name("permit").abi
    param_count = len(permit_abi["inputs"])

    # Try both nonce names
    try:
        nonce = token.functions.nonces(owner).call()
    except:
        nonce = token.functions._nonces(owner).call()

    # Expiry / deadline
    if not expiry:
        expiry = int(time.time()) + 3600  # default 1 hour

    # Prepare signing
    if param_count == 8:
        # DAI-style
        print("Detected: DAI-style permit")
        domain = {
            "name": "Dai Stablecoin",
            "version": "1",
            "chainId": w3.eth.chain_id,
            "verifyingContract": token_address
        }

        types = {
            "Permit": [
                {"name": "holder", "type": "address"},
                {"name": "spender", "type": "address"},
                {"name": "nonce", "type": "uint256"},
                {"name": "expiry", "type": "uint256"},
                {"name": "allowed", "type": "bool"},
            ]
        }

        message = {
            "holder": owner,
            "spender": spender,
            "nonce": nonce,
            "expiry": expiry,
            "allowed": max_approval
        }

        func_args = (owner, spender, nonce, expiry, max_approval)

    else:
        # ERC20Permit-style (EIP-2612)
        print("Detected: ERC20Permit-style")
        if amount is None:
            raise ValueError("Must provide `amount` for standard ERC20Permit")

        domain = {
            "name": token.functions.name().call(),
            "version": "1",
            "chainId": w3.eth.chain_id,
            "verifyingContract": token_address
        }

        types = {
            "Permit": [
                {"name": "owner", "type": "address"},
                {"name": "spender", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "nonce", "type": "uint256"},
                {"name": "deadline", "type": "uint256"},
            ]
        }

        message = {
            "owner": owner,
            "spender": spender,
            "value": amount,
            "nonce": nonce,
            "deadline": expiry
        }

        func_args = (owner, spender, amount, expiry)

    structured_data = {
        "types": dict(EIP712Domain=[
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ], **types),
        "domain": domain,
        "primaryType": "Permit",
        "message": message
    }

    # Sign typed data
    signable_message = encode_structured_data(structured_data)
    signed = acct.sign_message(signable_message)

    return token, (*func_args, signed.v, signed.r.to_bytes(32, "big"), signed.s.to_bytes(32, "big"))
    

def send_rescue(rescue_token: str, network: Literal["mainnet", "sepolia", "testnet"], chain: str = "eth") -> None:
    w3 = Web3(Web3.HTTPProvider(f"https://{chain}-{network}.g.alchemy.com/v2/{ALCHEMY_API_KEY}"))
    rescuer = Account.from_key(CLEAN_PRIVATE_KEY).address
    victim = Account.from_key(COMPROMISED_PRIVATE_KEY).address
    spender = TOKEN_PULLER_ADDRESS
    token, params = permit_token(w3, COMPROMISED_PRIVATE_KEY, rescue_token, spender, signer=CLEAN_PRIVATE_KEY, network=network)
    permit_call = token.encodeABI(fn_name="permit", args=[*params])
    
    ABI = [
        {
            "inputs": [
                {
                    "internalType": "address[]",
                    "name": "targets",
                    "type": "address[]"
                },
                {
                    "internalType": "bytes[]",
                    "name": "data",
                    "type": "bytes[]"
                }
            ],
            "name": "multicallExternal",
            "outputs": [],
            "stateMutability": "payable",
            "type": "function"
        },
        {
            "inputs": [
                {
                    "internalType": "address",
                    "name": "tokenAddress",
                    "type": "address"
                },
                {
                    "internalType": "address",
                    "name": "victimWallet",
                    "type": "address"
                }
            ],
            "name": "rescue",
            "outputs": [],
            "stateMutability": "payable",
            "type": "function"
        },
        {
            "inputs": [
                {
                    "internalType": "address",
                    "name": "_tokenRecipient",
                    "type": "address"
                }
            ],
            "stateMutability": "nonpayable",
            "type": "constructor"
        },
        {
            "inputs": [
                {
                    "internalType": "address",
                    "name": "_tokenRecipient",
                    "type": "address"
                }
            ],
            "name": "updateRecipient",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "owner",
            "outputs": [
                {
                    "internalType": "address",
                    "name": "",
                    "type": "address"
                }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "tokenRecipient",
            "outputs": [
                {
                    "internalType": "address",
                    "name": "",
                    "type": "address"
                }
            ],
            "stateMutability": "view",
            "type": "function"
        }
    ]

    puller = w3.eth.contract(address=Web3.to_checksum_address(TOKEN_PULLER_ADDRESS), abi=ABI)
    rescue_call = puller.encodeABI(fn_name="rescue", args=[rescue_token, victim])

    # ---------- multicall ----------
    targets = [rescue_token, TOKEN_PULLER_ADDRESS]
    calldata = [permit_call, rescue_call]

    tx = puller.functions.multicallExternal(targets, calldata).build_transaction({
        "from": rescuer,
        "nonce": w3.eth.get_transaction_count(rescuer),
        "gas": 300000,
        "maxFeePerGas": w3.to_wei("30", "gwei"),
        "maxPriorityFeePerGas": w3.to_wei("2", "gwei")
    })

    signed = w3.eth.account.sign_transaction(tx, CLEAN_PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    print("Multicall sent:", tx_hash.hex())

if __name__ == "__main__":
    # --- REAL-TIME LISTENER ---
    w3_ws = Web3(Web3.WebsocketProvider(ALCHEMY_WS))
    transfer_topic = w3.keccak(text="Transfer(address,address,uint256)").hex()
    comp_topic = "0x" + "00"*12 + COMPROMISED[2:].lower()

    sub = w3_ws.eth.filter({
        "topics": [transfer_topic, None, comp_topic]
    })

    print("⚡ Watching for incoming tokens...")

    while True:
        for log in sub.get_new_entries():
            token = log["address"]
            print(f"📥 Token detected: {token}")
            send_rescue(token)
