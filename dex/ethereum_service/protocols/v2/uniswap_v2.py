import asyncio
import logging
from decimal import Decimal
from typing import Dict, List, Any, Optional, Tuple
import sys
import os

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
from interfaces.base_engine import BaseProtocolAdapter

from ...engine import EthereumEngine
from ...config import EthereumConfig
from ...uniswap_helper import UniswapHelper
from ...abi_encoder import SwapCallDataEncoder

logger = logging.getLogger(__name__)

class UniswapV2Adapter(BaseProtocolAdapter):
    """Uniswap V2 protocol adapter"""
    
    def __init__(self, engine: EthereumEngine, config: EthereumConfig):
        self.engine = engine
        self.config = config
        self.router_address = config.UNISWAP_V2_ROUTER
        self.factory_address = config.UNISWAP_V2_FACTORY
        self.fee_rate = Decimal("0.003")  # 0.3% fee
        self.uniswap_helper = None
        
    async def initialize(self):
        """Initialize Uniswap V2 contracts"""
        logger.info("Initializing Uniswap V2 adapter...")
        if self.engine.w3:
            self.uniswap_helper = UniswapHelper(
                self.engine.w3,
                self.factory_address,
                self.config.UNISWAP_V3_FACTORY
            )
    
    async def get_pair_price(self, token_a: str, token_b: str) -> Decimal:
        """Get current price for token pair"""
        try:
            if not self.uniswap_helper:
                logger.error("UniswapHelper not initialized")
                return Decimal("0")
            
            # Get pair reserves using helper
            reserves = await self.uniswap_helper.get_v2_pair_reserves(token_a, token_b)
            if not reserves:
                return Decimal("0")
            
            reserve_a, reserve_b = reserves
            if reserve_a == 0 or reserve_b == 0:
                return Decimal("0")
            
            # Calculate price (token_b per token_a)
            price = self.uniswap_helper.calculate_v2_price(reserve_a, reserve_b)
            return price
            
        except Exception as e:
            logger.error(f"Error getting pair price {token_a}/{token_b}: {e}")
            return Decimal("0")
    
    async def get_liquidity(self, pair_address: str) -> Decimal:
        """Get total liquidity in pair"""
        try:
            # Get reserves and calculate USD liquidity
            # This is simplified - in production would need price feeds
            return Decimal("1000000")  # Placeholder for now
            
        except Exception as e:
            logger.error(f"Error getting liquidity for {pair_address}: {e}")
            return Decimal("0")
    
    async def build_swap_data(self, token_in: str, token_out: str, amount: Decimal) -> Dict:
        """Build swap transaction data with proper decimal handling"""
        try:
            if not self.engine.wallet_address or not self.engine.erc20_helper:
                raise ValueError("Wallet or ERC20Helper not available")
            
            # Get token decimals
            token_in_info = await self.engine.erc20_helper.get_token_info(token_in)
            token_out_info = await self.engine.erc20_helper.get_token_info(token_out)
            
            if not token_in_info or not token_out_info:
                raise ValueError("Could not get token information")
            
            # Calculate minimum amount out with slippage protection
            amount_out = await self.get_amount_out(amount, token_in, token_out)
            min_amount_out = amount_out * (1 - self.config.MAX_SLIPPAGE / 100)
            
            # Build real swap transaction with proper decimals
            transaction = SwapCallDataEncoder.build_v2_swap_transaction(
                self.router_address,
                token_in,
                token_out,
                amount,
                min_amount_out,
                self.engine.wallet_address,
                token_in_info["decimals"],
                token_out_info["decimals"]
            )
            
            return transaction
            
        except Exception as e:
            logger.error(f"Error building swap data: {e}")
            return {}
    
    async def get_amount_out(self, amount_in: Decimal, token_in: str, token_out: str) -> Decimal:
        """Calculate amount out for given input"""
        try:
            if not self.uniswap_helper:
                logger.error("UniswapHelper not initialized")
                return Decimal("0")
            
            reserves = await self.uniswap_helper.get_v2_pair_reserves(token_in, token_out)
            if not reserves:
                return Decimal("0")
            
            reserve_in, reserve_out = reserves
            
            # Use helper's calculation method
            amount_out = self.uniswap_helper.calculate_v2_amount_out(amount_in, reserve_in, reserve_out)
            return amount_out
            
        except Exception as e:
            logger.error(f"Error calculating amount out: {e}")
            return Decimal("0")
    
    async def get_pair_address(self, token_a: str, token_b: str) -> str:
        """Get pair contract address for two tokens"""
        try:
            # This would call the factory contract to get the pair address
            # For now, return a mock address
            return "0x1234567890abcdef1234567890abcdef12345678"
            
        except Exception as e:
            logger.error(f"Error getting pair address: {e}")
            return ""
    
    
    async def estimate_gas(self, swap_data: Dict) -> int:
        """Estimate gas for swap transaction"""
        try:
            # Uniswap V2 swaps typically use 120k-150k gas
            base_gas = 120000
            
            # Add extra gas for complex paths
            path_length = len(swap_data.get("params", {}).get("path", []))
            if path_length > 2:
                base_gas += (path_length - 2) * 30000
            
            return min(base_gas, 200000)  # Cap at 200k gas
            
        except Exception as e:
            logger.error(f"Error estimating gas: {e}")
            return 150000  # Default estimate