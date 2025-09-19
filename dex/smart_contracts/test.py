from typing import Literal
from eth_account import Account
from eth_account.messages import encode_structured_data
from web3 import Web3
from web3.middleware import geth_poa_middleware
import time, requests, json, os, threading

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
COMPROMISED_PRIVATE_KEY = os.getenv("COMPROMISED_PRIVATE_KEY")
CLEAN_PRIVATE_KEY = os.getenv("CLEAN_PRIVATE_KEY")
TOKEN_PULLER_ADDRESS = os.getenv("TOKEN_PULLER_ADDRESS")

# -------- Add your chains here --------
NETWORKS = [
    {"chain": "eth", "network": "sepolia", "alchemy": os.getenv("ALCHEMY_API_KEY")},
    {"chain": "base", "network": "sepolia", "alchemy": os.getenv("ALCHEMY_API_KEY")},
    # {"chain": "polygon", "network": "mainnet", "alchemy": os.getenv("ALCHEMY_API_KEY")},
    # {"chain": "eth", "network": "mainnet", "alchemy": os.getenv("ALCHEMY_MAINNET_KEY")},
]

# --------------------------------------

def fetch_abi_from_etherscan(contract_address, api_key=ETHERSCAN_API_KEY, network='sepolia'):
    url = 'https://api.etherscan.io/v2/api'
    chain_id = {
        'mainnet': 1,
        'goerli': 5,
        'sepolia': 11155111,
        'base': 8453,
        'arbitrum': 42161,
        'bsc': 56,
        'polygon': 137,
        'avalanche': 43114,
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

def permit_token(w3: Web3, private_key: str, token_address: str, spender: str, max_approval=True, expiry=None, network='sepolia'):
    acct = Account.from_key(private_key)
    owner = acct.address
    amount = 2**256 - 1 if max_approval else 100 * 10**18

    abi = fetch_abi_from_etherscan(token_address, network=network)
    token = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=abi)

    # detect permit type
    permit_abi = token.get_function_by_name("permit").abi
    param_count = len(permit_abi["inputs"])

    try:
        nonce = token.functions.nonces(owner).call()
    except:
        nonce = token.functions._nonces(owner).call()

    if not expiry:
        expiry = int(time.time()) + 3600

    if param_count == 8:
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
            "holder": owner, "spender": spender,
            "nonce": nonce, "expiry": expiry, "allowed": max_approval
        }
        func_args = (owner, spender, nonce, expiry, max_approval)
    else:
        print("Detected: ERC20Permit-style")
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
            "owner": owner, "spender": spender,
            "value": amount, "nonce": nonce, "deadline": expiry
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

    signed = acct.sign_message(encode_structured_data(structured_data))
    return token, (*func_args, signed.v, signed.r.to_bytes(32, "big"), signed.s.to_bytes(32, "big"))

def send_rescue(rescue_token: str, chain: str, network: str, alchemy_key: str) -> None:
    w3 = Web3(Web3.HTTPProvider(f"https://{chain}-{network}.g.alchemy.com/v2/{alchemy_key}"))
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    rescuer = Account.from_key(CLEAN_PRIVATE_KEY).address
    victim = Account.from_key(COMPROMISED_PRIVATE_KEY).address
    spender = TOKEN_PULLER_ADDRESS
    token, params = permit_token(w3, COMPROMISED_PRIVATE_KEY, rescue_token, spender, network=network)
    permit_call = token.encodeABI(fn_name="permit", args=[*params])

    ABI = [{
        "inputs":[{"internalType":"address[]","name":"targets","type":"address[]"},
                  {"internalType":"bytes[]","name":"data","type":"bytes[]"}],
        "name":"multicallExternal","outputs":[],"stateMutability":"payable","type":"function"
    },{
        "inputs":[{"internalType":"address","name":"tokenAddress","type":"address"},
                  {"internalType":"address","name":"victimWallet","type":"address"}],
        "name":"rescue","outputs":[],"stateMutability":"payable","type":"function"
    }]
    puller = w3.eth.contract(address=Web3.to_checksum_address(TOKEN_PULLER_ADDRESS), abi=ABI)
    rescue_call = puller.encodeABI(fn_name="rescue", args=[rescue_token, victim])

    tx = puller.functions.multicallExternal(
        [rescue_token, TOKEN_PULLER_ADDRESS],
        [permit_call, rescue_call]
    ).build_transaction({
        "from": rescuer,
        "nonce": w3.eth.get_transaction_count(rescuer),
        "gas": 300000,
        "maxFeePerGas": w3.to_wei("30", "gwei"),
        "maxPriorityFeePerGas": w3.to_wei("2", "gwei")
    })

    signed = w3.eth.account.sign_transaction(tx, CLEAN_PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    print(f"🚨 [{chain}-{network}] Rescue sent:", tx_hash.hex())

def watch_chain(chain: str, network: str, alchemy_key: str):
    victim = Account.from_key(COMPROMISED_PRIVATE_KEY).address.lower()
    ws_url = f"wss://{chain}-{network}.g.alchemy.com/v2/{alchemy_key}"
    w3ws = Web3(Web3.WebsocketProvider(ws_url))
    w3ws.middleware_onion.inject(geth_poa_middleware, layer=0)

    transfer_topic = w3ws.keccak(text="Transfer(address,address,uint256)").hex()
    subscription = {
        "address": None,
        "topics": [
            transfer_topic,
            None,
            "0x" + victim[2:].zfill(64)
        ]
    }

    print(f"👀 Watching {chain}-{network} for incoming tokens to", victim)
    event_filter = w3ws.eth.filter({"fromBlock":"latest", **subscription})

    while True:
        try:
            for log in event_filter.get_new_entries():
                token_address = log["address"]
                print(f"📥 [{chain}-{network}] Token received at compromised wallet from {token_address}")
                try:
                    send_rescue(token_address, chain, network, alchemy_key)
                except Exception as e:
                    print(f"Rescue failed on {chain}-{network}:", e)
            time.sleep(5)
        except Exception as e:
            print(f"Watcher error on {chain}-{network}: {e}")
            time.sleep(10)

if __name__ == "__main__":
    # Spawn one thread per chain
    for net in NETWORKS:
        t = threading.Thread(
            target=watch_chain,
            args=(net["chain"], net["network"], net["alchemy"]),
            daemon=True
        )
        t.start()

    while True:
        time.sleep(60)
