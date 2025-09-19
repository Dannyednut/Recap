import asyncio
import logging
import time
from decimal import Decimal
from typing import Dict, Any, Optional, Union
from web3 import Web3, AsyncWeb3
from web3.exceptions import Web3Exception
from eth_account import Account
from eth_utils import to_wei, from_wei
import sys
import os

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from base_engine import BaseEngine
from models.arbitrage_models import ExecutionResult

from .config import EthereumConfig
from .erc20_helper import ERC20Helper

logger = logging.getLogger(__name__)

class EthereumEngine(BaseEngine):
    """Ethereum blockchain engine for Web3 operations"""
    
    def __init__(self, config: EthereumConfig):
        self.config = config
        self.w3: Optional[AsyncWeb3] = None
        self.account: Optional[Account] = None
        self.wallet_address: Optional[str] = None
        self.erc20_helper: Optional[ERC20Helper] = None
        self.opportunities_cache = {}  # Store detected opportunities
        
    async def initialize(self) -> bool:
        """Initialize Web3 connection and wallet"""
        try:
            # Initialize Web3 connection
            self.w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.config.RPC_URL))
            
            # Check connection
            if not await self.w3.is_connected():
                raise ConnectionError("Failed to connect to Ethereum RPC")
            
            # Initialize wallet
            if self.config.PRIVATE_KEY:
                self.account = Account.from_key(self.config.PRIVATE_KEY)
                self.wallet_address = self.account.address
                self.erc20_helper = ERC20Helper(self.w3, self.wallet_address)
                logger.info(f"Wallet initialized: {self.wallet_address}")
            
            # Verify network
            chain_id = await self.w3.eth.chain_id
            if chain_id != self.config.CHAIN_ID:
                logger.warning(f"Chain ID mismatch: expected {self.config.CHAIN_ID}, got {chain_id}")
            
            logger.info(f"Ethereum engine initialized on chain {chain_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Ethereum engine: {e}")
            return False
    
    async def get_balance(self, token_address: str, wallet_address: str = None) -> Decimal:
        """Get token balance for wallet"""
        try:
            target_wallet = wallet_address or self.wallet_address
            if not target_wallet:
                raise ValueError("No wallet address provided")
            
            if self.erc20_helper:
                return await self.erc20_helper.get_balance(token_address)
            else:
                # Fallback for ETH only
                if token_address.lower() == "0x0" or token_address.upper() == "ETH":
                    balance_wei = await self.w3.eth.get_balance(target_wallet)
                    return Decimal(from_wei(balance_wei, 'ether'))
                else:
                    logger.warning("ERC20Helper not initialized, cannot get token balance")
                    return Decimal("0")
        except Exception as e:
            logger.error(f"Error getting balance for {token_address}: {e}")
            return Decimal("0")
    
    async def get_gas_price(self) -> Dict[str, int]:
        """Get current gas price using EIP-1559 or legacy"""
        try:
            # Try to get EIP-1559 gas price
            try:
                latest_block = await self.w3.eth.get_block('latest')
                if hasattr(latest_block, 'baseFeePerGas') and latest_block.baseFeePerGas:
                    # EIP-1559 transaction
                    base_fee = latest_block.baseFeePerGas
                    max_priority_fee = to_wei(2, 'gwei')  # 2 gwei tip
                    max_fee = int(base_fee * 2 + max_priority_fee)  # 2x base fee + tip
                    
                    # Cap at max gas price
                    max_cap = to_wei(self.config.MAX_GAS_PRICE_GWEI, 'gwei')
                    max_fee = min(max_fee, max_cap)
                    
                    return {
                        "maxFeePerGas": max_fee,
                        "maxPriorityFeePerGas": max_priority_fee,
                        "type": "eip1559"
                    }
            except Exception as eip_error:
                logger.debug(f"EIP-1559 not available: {eip_error}")
            
            # Fallback to legacy gas price
            gas_price = await self.w3.eth.gas_price
            adjusted_price = int(gas_price * self.config.GAS_PRICE_MULTIPLIER)
            
            # Cap at max gas price
            max_price = to_wei(self.config.MAX_GAS_PRICE_GWEI, 'gwei')
            return {
                "gasPrice": min(adjusted_price, max_price),
                "type": "legacy"
            }
            
        except Exception as e:
            logger.error(f"Error getting gas price: {e}")
            return {
                "gasPrice": to_wei(20, 'gwei'),
                "type": "legacy"
            }
    
    async def execute_transaction(self, tx_data: Dict[str, Any]) -> str:
        """Execute transaction and return tx hash"""
        try:
            if not self.account:
                raise ValueError("Wallet not initialized")
            
            # Get gas pricing
            gas_config = await self.get_gas_price()
            
            # Build transaction
            transaction = {
                'from': self.wallet_address,
                'gas': tx_data.get('gas', 200000),
                'nonce': await self.w3.eth.get_transaction_count(self.wallet_address),
                **tx_data
            }
            
            # Add gas pricing based on type
            if gas_config["type"] == "eip1559":
                transaction.update({
                    'maxFeePerGas': gas_config["maxFeePerGas"],
                    'maxPriorityFeePerGas': gas_config["maxPriorityFeePerGas"],
                    'type': 2  # EIP-1559 transaction type
                })
            else:
                transaction['gasPrice'] = gas_config["gasPrice"]
            
            # Estimate gas if not provided
            if 'gas' not in tx_data:
                try:
                    estimated_gas = await self.w3.eth.estimate_gas(transaction)
                    transaction['gas'] = int(estimated_gas * 1.2)  # Add 20% buffer
                except Exception as gas_error:
                    logger.warning(f"Gas estimation failed: {gas_error}")
                    transaction['gas'] = 200000  # Fallback
            
            # Sign transaction
            signed_txn = self.account.sign_transaction(transaction)
            
            # Send transaction
            tx_hash = await self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            logger.info(f"Transaction sent: {tx_hash.hex()}")
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Error executing Ethereum transaction: {e}")
            raise
    
    async def call_contract(
        self,
        contract_address: str,
        function_name: str,
        params: list
    ) -> Any:
        """Call contract function"""
        try:
            if function_name == "getPair":
                factory_abi = [
                    {
                        "constant": True,
                        "inputs": [
                            {"name": "tokenA", "type": "address"},
                            {"name": "tokenB", "type": "address"}
                        ],
                        "name": "getPair",
                        "outputs": [{"name": "pair", "type": "address"}],
                        "type": "function"
                    }
                ]
                contract = self.w3.eth.contract(address=contract_address, abi=factory_abi)
                return await contract.functions.getPair(params[0], params[1]).call()
            
            elif function_name == "getReserves":
                pair_abi = [
                    {
                        "constant": True,
                        "inputs": [],
                        "name": "getReserves",
                        "outputs": [
                            {"name": "_reserve0", "type": "uint112"},
                            {"name": "_reserve1", "type": "uint112"},
                            {"name": "_blockTimestampLast", "type": "uint32"}
                        ],
                        "type": "function"
                    }
                ]
                contract = self.w3.eth.contract(address=contract_address, abi=pair_abi)
                return await contract.functions.getReserves().call()
            
            elif function_name == "token0":
                pair_abi = [
                    {
                        "constant": True,
                        "inputs": [],
                        "name": "token0",
                        "outputs": [{"name": "", "type": "address"}],
                        "type": "function"
                    }
                ]
                contract = self.w3.eth.contract(address=contract_address, abi=pair_abi)
                return await contract.functions.token0().call()
            
            else:
                raise ValueError(f"Unsupported function: {function_name}")
                
        except Exception as e:
            logger.error(f"Error calling contract function {function_name}: {e}")
            raise
    
    async def build_transaction(
        self,
        contract_address: str,
        function_name: str,
        params: list
    ) -> Dict[str, Any]:
        """Build transaction data for contract call"""
        try:
            return {
                "to": contract_address,
                "data": "0x",
                "value": 0
            }
        except Exception as e:
            logger.error(f"Error building transaction: {e}")
            raise
    
    async def wait_for_transaction(self, tx_hash: str) -> Dict[str, Any]:
        """Wait for transaction confirmation"""
        try:
            receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            return {
                "success": receipt.status == 1,
                "gas_used": receipt.gasUsed,
                "block_number": receipt.blockNumber,
                "transaction_hash": tx_hash
            }
            
        except Exception as e:
            logger.error(f"Error waiting for Ethereum transaction: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_block_number(self) -> int:
        """Get latest block number"""
        return await self.w3.eth.block_number
    
    async def estimate_gas(self, tx_data: Dict[str, Any]) -> int:
        """Estimate gas for transaction"""
        try:
            return await self.w3.eth.estimate_gas(tx_data)
        except Exception as e:
            logger.error(f"Error estimating gas: {e}")
            return 200000  # Default gas limit
    
    async def wait_for_transaction(self, tx_hash: str, timeout: int = 120) -> ExecutionResult:
        """Wait for transaction confirmation"""
        try:
            receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
            
            return ExecutionResult(
                tx_hash=tx_hash,
                status="success" if receipt.status == 1 else "failed",
                gas_used=receipt.gasUsed,
                gas_price=receipt.effectiveGasPrice
            )
        except Exception as e:
            logger.error(f"Error waiting for transaction {tx_hash}: {e}")
            return ExecutionResult(
                tx_hash=tx_hash,
                status="failed",
                gas_used=0,
                gas_price=0,
                error_message=str(e)
            )
    
    # BaseEngine abstract method implementations
    def get_web3_instance(self):
        """Get the web3 instance"""
        return self.w3
    
    def get_account(self):
        """Get the account used for transactions"""
        return self.account
    
    async def get_contract(self, address: str, abi: list):
        """Get a contract instance at the specified address"""
        return self.w3.eth.contract(address=address, abi=abi)
    
    async def get_token_balance(self, token_address: str, account_address: str) -> int:
        """Get token balance for an account"""
        try:
            if token_address.lower() == "0x0" or token_address.upper() == "ETH":
                balance_wei = await self.w3.eth.get_balance(account_address)
                return balance_wei
            else:
                # ERC20 token balance
                erc20_abi = [
                    {
                        "constant": True,
                        "inputs": [{"name": "_owner", "type": "address"}],
                        "name": "balanceOf",
                        "outputs": [{"name": "balance", "type": "uint256"}],
                        "type": "function"
                    }
                ]
                contract = self.w3.eth.contract(address=token_address, abi=erc20_abi)
                return await contract.functions.balanceOf(account_address).call()
        except Exception as e:
            logger.error(f"Error getting token balance: {e}")
            return 0
    
    async def get_native_balance(self, account_address: str) -> int:
        """Get native token (ETH) balance for an account"""
        try:
            return await self.w3.eth.get_balance(account_address)
        except Exception as e:
            logger.error(f"Error getting native balance: {e}")
            return 0
    
    async def get_gas_price(self) -> int:
        """Get current gas price"""
        try:
            return await self.w3.eth.gas_price
        except Exception as e:
            logger.error(f"Error getting gas price: {e}")
            return 20000000000  # 20 gwei default
    
    async def estimate_gas(self, tx: dict) -> int:
        """Estimate gas for a transaction"""
        try:
            return await self.w3.eth.estimate_gas(tx)
        except Exception as e:
            logger.error(f"Error estimating gas: {e}")
            return 200000  # Default gas limit
    
    async def send_transaction(self, tx: dict) -> str:
        """Send a transaction and return the transaction hash"""
        try:
            if not self.account:
                raise ValueError("Wallet not initialized")
            
            # Add nonce if not present
            if 'nonce' not in tx:
                tx['nonce'] = await self.w3.eth.get_transaction_count(self.wallet_address)
            
            # Sign and send transaction
            signed_txn = self.account.sign_transaction(tx)
            tx_hash = await self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            return tx_hash.hex()
        except Exception as e:
            logger.error(f"Error sending transaction: {e}")
            raise
    
    async def wait_for_transaction_receipt(self, tx_hash: str, timeout: int = 120) -> dict:
        """Wait for a transaction receipt"""
        try:
            receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
            return dict(receipt)
        except Exception as e:
            logger.error(f"Error waiting for transaction receipt: {e}")
            raise
    
    async def get_block(self, block_identifier) -> dict:
        """Get block information"""
        try:
            block = await self.w3.eth.get_block(block_identifier)
            return dict(block)
        except Exception as e:
            logger.error(f"Error getting block: {e}")
            raise
    
    async def get_transaction(self, tx_hash: str) -> dict:
        """Get transaction information"""
        try:
            tx = await self.w3.eth.get_transaction(tx_hash)
            return dict(tx)
        except Exception as e:
            logger.error(f"Error getting transaction: {e}")
            raise
    
    async def get_transaction_count(self, address: str) -> int:
        """Get transaction count (nonce) for an address"""
        try:
            return await self.w3.eth.get_transaction_count(address)
        except Exception as e:
            logger.error(f"Error getting transaction count: {e}")
            return 0
    
    async def get_chain_id(self) -> int:
        """Get the chain ID"""
        try:
            return await self.w3.eth.chain_id
        except Exception as e:
            logger.error(f"Error getting chain ID: {e}")
            return self.config.CHAIN_ID
    
    def get_network_name(self) -> str:
        """Get the network name"""
        return "ethereum"
    
    async def is_contract(self, address: str) -> bool:
        """Check if an address is a contract"""
        try:
            code = await self.w3.eth.get_code(address)
            return len(code) > 0
        except Exception as e:
            logger.error(f"Error checking if address is contract: {e}")
            return False
    
    async def get_logs(self, filter_params: dict) -> list:
        """Get logs matching the filter parameters"""
        try:
            logs = await self.w3.eth.get_logs(filter_params)
            return [dict(log) for log in logs]
        except Exception as e:
            logger.error(f"Error getting logs: {e}")
            return []
    
    async def call_function(self, contract, function_name: str, *args, **kwargs):
        """Call a contract function"""
        try:
            function = getattr(contract.functions, function_name)
            return await function(*args, **kwargs).call()
        except Exception as e:
            logger.error(f"Error calling contract function {function_name}: {e}")
            raise
    
    async def deploy_contract(self, abi: list, bytecode: str, *args) -> str:
        """Deploy a contract and return its address"""
        try:
            if not self.account:
                raise ValueError("Wallet not initialized")
            
            contract = self.w3.eth.contract(abi=abi, bytecode=bytecode)
            
            # Build constructor transaction
            constructor_tx = contract.constructor(*args).build_transaction({
                'from': self.wallet_address,
                'nonce': await self.w3.eth.get_transaction_count(self.wallet_address),
                'gasPrice': await self.w3.eth.gas_price,
            })
            
            # Estimate gas
            constructor_tx['gas'] = await self.w3.eth.estimate_gas(constructor_tx)
            
            # Sign and send transaction
            signed_txn = self.account.sign_transaction(constructor_tx)
            tx_hash = await self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            # Wait for receipt to get contract address
            receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash)
            return receipt.contractAddress
            
        except Exception as e:
            logger.error(f"Error deploying contract: {e}")
            raise
    
    async def save_opportunity(self, opportunity, opportunity_type: str) -> bool:
        """Save detected arbitrage opportunity to cache"""
        try:
            opportunity_id = getattr(opportunity, 'opportunity_id', f"opp_{int(time.time())}")
            self.opportunities_cache[opportunity_id] = {
                'opportunity': opportunity,
                'type': opportunity_type,
                'timestamp': time.time(),
                'status': 'detected'
            }
            logger.debug(f"Saved opportunity {opportunity_id} to cache")
            return True
        except Exception as e:
            logger.error(f"Error saving opportunity: {e}")
            return False
    
    async def get_opportunities(self, max_age_seconds: int = 300) -> list:
        """Get cached opportunities that are still fresh"""
        try:
            current_time = time.time()
            fresh_opportunities = []
            
            for opp_id, opp_data in self.opportunities_cache.items():
                if current_time - opp_data['timestamp'] <= max_age_seconds:
                    fresh_opportunities.append(opp_data['opportunity'])
            
            return fresh_opportunities
        except Exception as e:
            logger.error(f"Error getting opportunities: {e}")
            return []
    
    async def clear_stale_opportunities(self, max_age_seconds: int = 300) -> None:
        """Clear opportunities older than max_age_seconds"""
        try:
            current_time = time.time()
            stale_keys = []
            
            for opp_id, opp_data in self.opportunities_cache.items():
                if current_time - opp_data['timestamp'] > max_age_seconds:
                    stale_keys.append(opp_id)
            
            for key in stale_keys:
                del self.opportunities_cache[key]
                
            if stale_keys:
                logger.debug(f"Cleared {len(stale_keys)} stale opportunities")
        except Exception as e:
            logger.error(f"Error clearing stale opportunities: {e}")