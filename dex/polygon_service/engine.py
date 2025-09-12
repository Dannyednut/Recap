import asyncio
import logging
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
from interfaces.base_engine import BaseEngine
from models.arbitrage_models import ExecutionResult

from .config import PolygonConfig

logger = logging.getLogger(__name__)

class PolygonEngine(BaseEngine):
    """Polygon blockchain engine for Web3 operations"""
    
    def __init__(self, config: PolygonConfig):
        self.config = config
        self.w3: Optional[AsyncWeb3] = None
        self.account: Optional[Account] = None
        self.wallet_address: Optional[str] = None
        
    async def initialize(self) -> bool:
        """Initialize Web3 connection and wallet"""
        try:
            # Initialize Web3 connection
            self.w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.config.RPC_URL))
            
            # Check connection
            if not await self.w3.is_connected():
                raise ConnectionError("Failed to connect to Polygon RPC")
            
            # Initialize wallet
            if self.config.PRIVATE_KEY:
                self.account = Account.from_key(self.config.PRIVATE_KEY)
                self.wallet_address = self.account.address
                logger.info(f"Polygon Wallet initialized: {self.wallet_address}")
            
            # Verify network
            chain_id = await self.w3.eth.chain_id
            if chain_id != self.config.CHAIN_ID:
                logger.warning(f"Polygon Chain ID mismatch: expected {self.config.CHAIN_ID}, got {chain_id}")
            
            logger.info(f"Polygon engine initialized on chain {chain_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Polygon engine: {e}")
            return False
    
    async def get_balance(self, token_address: str, wallet_address: str = None) -> Decimal:
        """Get token balance for wallet"""
        try:
            target_wallet = wallet_address or self.wallet_address
            if not target_wallet:
                raise ValueError("No wallet address provided")
            
            # MATIC balance
            if token_address.lower() == "0x0" or token_address.upper() == "MATIC":
                balance_wei = await self.w3.eth.get_balance(target_wallet)
                return Decimal(from_wei(balance_wei, 'ether'))
            else:
                # ERC20 token balance
                erc20_abi = [
                    {
                        "constant": True,
                        "inputs": [{"name": "_owner", "type": "address"}],
                        "name": "balanceOf",
                        "outputs": [{"name": "balance", "type": "uint256"}],
                        "type": "function"
                    },
                    {
                        "constant": True,
                        "inputs": [],
                        "name": "decimals",
                        "outputs": [{"name": "", "type": "uint8"}],
                        "type": "function"
                    }
                ]
                
                contract = self.w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=erc20_abi)
                balance_wei = await contract.functions.balanceOf(target_wallet).call()
                decimals = await contract.functions.decimals().call()
                
                return Decimal(balance_wei) / Decimal(10 ** decimals)
                
        except Exception as e:
            logger.error(f"Error getting Polygon balance for {token_address}: {e}")
            return Decimal("0")
    
    async def get_gas_price(self) -> Dict[str, int]:
        """Get current gas price (Polygon uses EIP-1559)"""
        try:
            # Get gas price data
            latest_block = await self.w3.eth.get_block('latest')
            base_fee = latest_block.get('baseFeePerGas', to_wei(30, 'gwei'))
            
            # Calculate priority fee
            priority_fee = to_wei(self.config.MAX_PRIORITY_FEE_PER_GAS_GWEI, 'gwei')
            
            # Calculate max fee per gas
            max_fee = base_fee + priority_fee
            max_fee_cap = to_wei(self.config.MAX_FEE_PER_GAS_GWEI, 'gwei')
            
            final_max_fee = min(max_fee, max_fee_cap)
            
            return {
                "maxFeePerGas": int(final_max_fee * self.config.GAS_PRICE_MULTIPLIER),
                "maxPriorityFeePerGas": priority_fee,
                "type": "eip1559"
            }
            
        except Exception as e:
            logger.error(f"Error getting Polygon gas price: {e}")
            # Fallback to legacy pricing
            return {
                "gasPrice": to_wei(50, 'gwei'),
                "type": "legacy"
            }
    
    async def estimate_gas(self, transaction: Dict[str, Any]) -> int:
        """Estimate gas for transaction"""
        try:
            gas_estimate = await self.w3.eth.estimate_gas(transaction)
            # Add 20% buffer for Polygon
            return int(gas_estimate * 1.2)
            
        except Exception as e:
            logger.error(f"Error estimating Polygon gas: {e}")
            return 150000  # Default fallback
    
    async def execute_transaction(self, transaction_data: Dict[str, Any]) -> str:
        """Execute transaction on Polygon"""
        try:
            if not self.account or not self.wallet_address:
                raise ValueError("Wallet not initialized")
            
            # Get current nonce
            nonce = await self.w3.eth.get_transaction_count(self.wallet_address)
            
            # Get gas price
            gas_info = await self.get_gas_price()
            
            # Build transaction
            transaction = {
                "to": transaction_data.get("to"),
                "value": transaction_data.get("value", 0),
                "data": transaction_data.get("data", "0x"),
                "gas": transaction_data.get("gas") or await self.estimate_gas(transaction_data),
                "nonce": nonce,
                "chainId": self.config.CHAIN_ID
            }
            
            # Add gas pricing
            if gas_info["type"] == "eip1559":
                transaction["maxFeePerGas"] = gas_info["maxFeePerGas"]
                transaction["maxPriorityFeePerGas"] = gas_info["maxPriorityFeePerGas"]
            else:
                transaction["gasPrice"] = gas_info["gasPrice"]
            
            # Sign transaction
            signed_txn = self.account.sign_transaction(transaction)
            
            # Send transaction
            tx_hash = await self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            logger.info(f"Polygon Transaction sent: {tx_hash.hex()}")
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Error executing Polygon transaction: {e}")
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
            logger.error(f"Error waiting for Polygon transaction: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def wait_for_transaction_receipt(self, tx_hash: str, timeout: int = 60) -> Dict[str, Any]:
        """Wait for transaction confirmation"""
        try:
            receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
            return {
                "success": receipt.status == 1,
                "blockNumber": receipt.blockNumber,
                "gasUsed": receipt.gasUsed,
                "receipt": receipt
            }
            
        except Exception as e:
            logger.error(f"Error waiting for Polygon transaction receipt: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_current_block(self) -> int:
        """Get current block number"""
        try:
            return await self.w3.eth.block_number
        except Exception as e:
            logger.error(f"Error getting Polygon block number: {e}")
            return 0
    
    async def shutdown(self) -> None:
        """Shutdown engine"""
        try:
            if self.w3:
                # Close any open connections
                pass
            logger.info("Polygon engine shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down Polygon engine: {e}")