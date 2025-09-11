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

from .config import BSCConfig

logger = logging.getLogger(__name__)

class BSCEngine(BaseEngine):
    """BSC (Binance Smart Chain) blockchain engine for Web3 operations"""
    
    def __init__(self, config: BSCConfig):
        self.config = config
        self.w3: Optional[AsyncWeb3] = None
        self.account: Optional[Account] = None
        self.wallet_address: Optional[str] = None
        
    async def initialize(self) -> None:
        """Initialize Web3 connection and wallet"""
        try:
            # Initialize Web3 connection
            self.w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.config.RPC_URL))
            
            # Check connection
            if not await self.w3.is_connected():
                raise ConnectionError("Failed to connect to BSC RPC")
            
            # Initialize wallet
            if self.config.PRIVATE_KEY:
                self.account = Account.from_key(self.config.PRIVATE_KEY)
                self.wallet_address = self.account.address
                logger.info(f"BSC Wallet initialized: {self.wallet_address}")
            
            # Verify network
            chain_id = await self.w3.eth.chain_id
            if chain_id != self.config.CHAIN_ID:
                logger.warning(f"BSC Chain ID mismatch: expected {self.config.CHAIN_ID}, got {chain_id}")
            
            logger.info(f"BSC engine initialized on chain {chain_id}")
            
        except Exception as e:
            logger.error(f"Failed to initialize BSC engine: {e}")
            raise
    
    async def get_balance(self, token_address: str, wallet_address: str = None) -> Decimal:
        """Get token balance for wallet"""
        try:
            target_wallet = wallet_address or self.wallet_address
            if not target_wallet:
                raise ValueError("No wallet address provided")
            
            # BNB balance
            if token_address.lower() == "0x0" or token_address.upper() == "BNB":
                balance_wei = await self.w3.eth.get_balance(target_wallet)
                return Decimal(from_wei(balance_wei, 'ether'))
            else:
                # ERC20 token balance (using standard ERC20 ABI)
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
            logger.error(f"Error getting BSC balance for {token_address}: {e}")
            return Decimal("0")
    
    async def get_gas_price(self) -> Dict[str, int]:
        """Get current gas price (BSC uses legacy gas pricing)"""
        try:
            # BSC primarily uses legacy gas pricing
            gas_price = await self.w3.eth.gas_price
            
            # Apply multiplier and cap
            adjusted_gas_price = int(gas_price * self.config.GAS_PRICE_MULTIPLIER)
            max_gas_price = to_wei(self.config.MAX_GAS_PRICE_GWEI, 'gwei')
            
            final_gas_price = min(adjusted_gas_price, max_gas_price)
            
            return {
                "gasPrice": final_gas_price,
                "type": "legacy"
            }
            
        except Exception as e:
            logger.error(f"Error getting BSC gas price: {e}")
            # Fallback to 5 gwei
            return {
                "gasPrice": to_wei(5, 'gwei'),
                "type": "legacy"
            }
    
    async def estimate_gas(self, transaction: Dict[str, Any]) -> int:
        """Estimate gas for transaction"""
        try:
            gas_estimate = await self.w3.eth.estimate_gas(transaction)
            # Add 20% buffer for BSC
            return int(gas_estimate * 1.2)
            
        except Exception as e:
            logger.error(f"Error estimating BSC gas: {e}")
            return 100000  # Default fallback
    
    async def execute_transaction(self, transaction_data: Dict[str, Any]) -> str:
        """Execute transaction on BSC"""
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
                "gasPrice": gas_info["gasPrice"],
                "nonce": nonce,
                "chainId": self.config.CHAIN_ID
            }
            
            # Sign transaction
            signed_txn = self.account.sign_transaction(transaction)
            
            # Send transaction
            tx_hash = await self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            logger.info(f"BSC Transaction sent: {tx_hash.hex()}")
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Error executing BSC transaction: {e}")
            raise
    
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
            logger.error(f"Error waiting for BSC transaction receipt: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_current_block(self) -> int:
        """Get current block number"""
        try:
            return await self.w3.eth.block_number
        except Exception as e:
            logger.error(f"Error getting BSC block number: {e}")
            return 0
    
    async def shutdown(self) -> None:
        """Shutdown engine"""
        try:
            if self.w3:
                # Close any open connections
                pass
            logger.info("BSC engine shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down BSC engine: {e}")