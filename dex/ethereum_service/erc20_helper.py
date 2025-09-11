import asyncio
import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from web3 import Web3
from eth_abi import encode, decode

logger = logging.getLogger(__name__)

class ERC20Helper:
    """Helper class for ERC20 token operations"""
    
    # Standard ERC20 ABI (minimal)
    ERC20_ABI = [
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [
                {"name": "_owner", "type": "address"},
                {"name": "_spender", "type": "address"}
            ],
            "name": "allowance", 
            "outputs": [{"name": "remaining", "type": "uint256"}],
            "type": "function"
        },
        {
            "constant": False,
            "inputs": [
                {"name": "_spender", "type": "address"},
                {"name": "_value", "type": "uint256"}
            ],
            "name": "approve",
            "outputs": [{"name": "success", "type": "bool"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "symbol",
            "outputs": [{"name": "", "type": "string"}],
            "type": "function"
        }
    ]
    
    def __init__(self, w3, wallet_address: str):
        self.w3 = w3
        self.wallet_address = wallet_address
        
    async def get_balance(self, token_address: str) -> Decimal:
        """Get ERC20 token balance"""
        try:
            if token_address.lower() == "0x0" or token_address.upper() == "ETH":
                # Native ETH balance
                balance_wei = await self.w3.eth.get_balance(self.wallet_address)
                return Decimal(str(balance_wei)) / Decimal("1e18")
            
            # Get token contract
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=self.ERC20_ABI
            )
            
            # Get balance
            balance = await contract.functions.balanceOf(self.wallet_address).call()
            
            # Get decimals
            decimals = await contract.functions.decimals().call()
            
            # Convert to decimal with proper scaling
            return Decimal(str(balance)) / Decimal(f"1e{decimals}")
            
        except Exception as e:
            logger.error(f"Error getting ERC20 balance for {token_address}: {e}")
            return Decimal("0")
    
    async def get_allowance(self, token_address: str, spender_address: str) -> Decimal:
        """Get ERC20 allowance for spender"""
        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=self.ERC20_ABI
            )
            
            allowance = await contract.functions.allowance(
                self.wallet_address,
                spender_address
            ).call()
            
            # Get decimals for proper scaling
            decimals = await contract.functions.decimals().call()
            
            return Decimal(str(allowance)) / Decimal(f"1e{decimals}")
            
        except Exception as e:
            logger.error(f"Error getting allowance: {e}")
            return Decimal("0")
    
    async def build_approve_transaction(self, token_address: str, spender_address: str, amount: Decimal) -> Dict[str, Any]:
        """Build approve transaction data"""
        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=self.ERC20_ABI
            )
            
            # Get decimals
            decimals = await contract.functions.decimals().call()
            
            # Convert amount to wei
            amount_wei = int(amount * Decimal(f"1e{decimals}"))
            
            # Build transaction
            transaction = contract.functions.approve(
                spender_address,
                amount_wei
            ).build_transaction({
                'from': self.wallet_address,
                'gas': 60000,  # Standard approve gas
                'gasPrice': 0,  # Will be set by engine
                'nonce': 0      # Will be set by engine
            })
            
            return transaction
            
        except Exception as e:
            logger.error(f"Error building approve transaction: {e}")
            return {}
    
    async def get_token_info(self, token_address: str) -> Dict[str, Any]:
        """Get basic token information"""
        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=self.ERC20_ABI
            )
            
            symbol = await contract.functions.symbol().call()
            decimals = await contract.functions.decimals().call()
            
            return {
                "address": token_address,
                "symbol": symbol,
                "decimals": decimals
            }
            
        except Exception as e:
            logger.error(f"Error getting token info: {e}")
            return {}
    
    def encode_transfer_data(self, to_address: str, amount: int) -> str:
        """Encode transfer function call data"""
        try:
            # transfer(address,uint256) function selector
            function_selector = "0xa9059cbb"
            
            # Encode parameters
            encoded_params = encode(['address', 'uint256'], [to_address, amount])
            
            return function_selector + encoded_params.hex()
            
        except Exception as e:
            logger.error(f"Error encoding transfer data: {e}")
            return ""