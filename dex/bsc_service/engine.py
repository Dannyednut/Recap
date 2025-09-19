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

from .config import BSCConfig

logger = logging.getLogger(__name__)

class BSCEngine(BaseEngine):
    """BSC (Binance Smart Chain) blockchain engine for Web3 operations"""
    
    def __init__(self, config: BSCConfig):
        self.config = config
        self.w3: Optional[AsyncWeb3] = None
        self.account: Optional[Account] = None
        self.wallet_address: Optional[str] = None
        self.opportunities_cache = {}  # Store detected opportunities
        
    async def initialize(self) -> bool:
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
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize BSC engine: {e}")
            return False
    
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
    
    async def call_contract(
        self,
        contract_address: str,
        function_name: str,
        params: list
    ) -> Any:
        """Call contract function"""
        try:
            # This is a simplified implementation
            # In production, you would need proper ABI for each contract
            if function_name == "getPair":
                # Factory.getPair(tokenA, tokenB)
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
                # Pair.getReserves()
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
                # Pair.token0()
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
            
            elif function_name == "quoteExactInputSingle":
                # Quoter.quoteExactInputSingle()
                quoter_abi = [
                    {
                        "inputs": [
                            {"name": "tokenIn", "type": "address"},
                            {"name": "tokenOut", "type": "address"},
                            {"name": "fee", "type": "uint24"},
                            {"name": "amountIn", "type": "uint256"},
                            {"name": "sqrtPriceLimitX96", "type": "uint160"}
                        ],
                        "name": "quoteExactInputSingle",
                        "outputs": [{"name": "amountOut", "type": "uint256"}],
                        "type": "function"
                    }
                ]
                contract = self.w3.eth.contract(address=contract_address, abi=quoter_abi)
                return await contract.functions.quoteExactInputSingle(
                    params[0], params[1], params[2], params[3], params[4]
                ).call()
            
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
            # Simplified transaction building
            return {
                "to": contract_address,
                "data": "0x",  # Would contain encoded function call
                "value": 0
            }
        except Exception as e:
            logger.error(f"Error building transaction: {e}")
            raise
    
    async def wait_for_transaction(self, tx_hash: str) -> Dict[str, Any]:
        """Wait for transaction confirmation"""
        try:
            # Wait for transaction receipt
            receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            return {
                "success": receipt.status == 1,
                "gas_used": receipt.gasUsed,
                "block_number": receipt.blockNumber,
                "transaction_hash": tx_hash
            }
            
        except Exception as e:
            logger.error(f"Error waiting for BSC transaction: {e}")
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
            if token_address.lower() == "0x0" or token_address.upper() == "BNB":
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
        """Get native token (BNB) balance for an account"""
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
            return 5000000000  # 5 gwei default
    
    async def estimate_gas(self, tx: dict) -> int:
        """Estimate gas for a transaction"""
        try:
            return await self.w3.eth.estimate_gas(tx)
        except Exception as e:
            logger.error(f"Error estimating gas: {e}")
            return 100000  # Default gas limit
    
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
        return "bsc"
    
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