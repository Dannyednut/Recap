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
from ...quoter_helper import UniswapV3QuoterHelper

logger = logging.getLogger(__name__)

class UniswapV3Adapter(BaseProtocolAdapter):
    """Uniswap V3 protocol adapter with concentrated liquidity"""
    
    def __init__(self, engine: EthereumEngine, config: EthereumConfig):
        self.engine = engine
        self.config = config
        self.router_address = config.UNISWAP_V3_ROUTER
        self.factory_address = config.UNISWAP_V3_FACTORY
        self.quoter_address = config.UNISWAP_V3_QUOTER_V2
        self.uniswap_helper = None
        self.quoter_helper = None
        
        # Common fee tiers in basis points
        self.fee_tiers = {
            "0.01%": 100,    # Stable pairs
            "0.05%": 500,    # Standard pairs
            "0.30%": 3000,   # Exotic pairs
            "1.00%": 10000   # Very exotic pairs
        }
        
    async def initialize(self):
        """Initialize Uniswap V3 contracts"""
        logger.info("Initializing Uniswap V3 adapter...")
        if self.engine.w3:
            self.uniswap_helper = UniswapHelper(
                self.engine.w3,
                self.config.UNISWAP_V2_FACTORY,
                self.factory_address
            )
            self.quoter_helper = UniswapV3QuoterHelper(
                self.engine.w3,
                self.quoter_address
            )
    
    async def get_pair_price(self, token_a: str, token_b: str, fee_tier: int = 3000) -> Decimal:
        """Get current price for token pair with specific fee tier"""
        try:
            if not self.uniswap_helper:
                logger.error("UniswapHelper not initialized")
                return Decimal("0")
            
            # Get pool data for the fee tier
            pool_data = await self.uniswap_helper.get_v3_pool_data(token_a, token_b, fee_tier)
            if not pool_data:
                return Decimal("0")
            
            # Extract current price from sqrtPriceX96
            sqrt_price_x96 = pool_data.get("sqrtPriceX96", 0)
            if sqrt_price_x96 == 0:
                return Decimal("0")
            
            # Convert sqrtPriceX96 to actual price
            price = self.uniswap_helper.sqrt_price_to_price(sqrt_price_x96)
            return price
            
        except Exception as e:
            logger.error(f"Error getting V3 pair price {token_a}/{token_b}: {e}")
            return Decimal("0")
    
    async def get_liquidity(self, pair_address: str) -> Decimal:
        """Get active liquidity in V3 pool"""
        try:
            # This would call the pool contract to get liquidity
            # V3 has concentrated liquidity, so this is the active liquidity
            return Decimal("500000")  # $500K active liquidity
            
        except Exception as e:
            logger.error(f"Error getting V3 liquidity for {pair_address}: {e}")
            return Decimal("0")
    
    async def build_swap_data(self, token_in: str, token_out: str, amount: Decimal, fee_tier: int = 3000) -> Dict:
        """Build V3 swap transaction data with proper decimal handling"""
        try:
            if not self.engine.wallet_address or not self.engine.erc20_helper:
                raise ValueError("Wallet or ERC20Helper not available")
            
            # Get token decimals
            token_in_info = await self.engine.erc20_helper.get_token_info(token_in)
            token_out_info = await self.engine.erc20_helper.get_token_info(token_out)
            
            if not token_in_info or not token_out_info:
                raise ValueError("Could not get token information")
            
            # Calculate minimum amount out
            amount_out = await self.get_amount_out(amount, token_in, token_out, fee_tier)
            min_amount_out = amount_out * (1 - self.config.MAX_SLIPPAGE / 100)
            
            # Build real swap transaction with proper decimals
            transaction = SwapCallDataEncoder.build_v3_swap_transaction(
                self.router_address,
                token_in,
                token_out,
                fee_tier,
                amount,
                min_amount_out,
                self.engine.wallet_address,
                token_in_info["decimals"],
                token_out_info["decimals"]
            )
            
            return transaction
            
        except Exception as e:
            logger.error(f"Error building V3 swap data: {e}")
            return {}
    
    async def get_amount_out(self, amount_in: Decimal, token_in: str, token_out: str, fee_tier: int = 3000) -> Decimal:
        """Calculate amount out using V3 Quoter for accuracy"""
        try:
            if not self.quoter_helper or not self.engine.erc20_helper:
                logger.warning("Quoter or ERC20Helper not initialized, falling back to pool price")
                return await self._get_amount_out_fallback(amount_in, token_in, token_out, fee_tier)
            
            # Get token decimals for proper conversion
            token_in_info = await self.engine.erc20_helper.get_token_info(token_in)
            token_out_info = await self.engine.erc20_helper.get_token_info(token_out)
            
            if not token_in_info or not token_out_info:
                logger.warning("Could not get token info, falling back to pool price")
                return await self._get_amount_out_fallback(amount_in, token_in, token_out, fee_tier)
            
            # Use real Quoter for accurate quotes
            amount_out = await self.quoter_helper.get_optimal_amount_out(
                token_in,
                token_out,
                amount_in,
                token_in_info["decimals"],
                token_out_info["decimals"],
                fee_tier
            )
            
            return amount_out
            
        except Exception as e:
            logger.error(f"Error calculating V3 amount out: {e}")
            return await self._get_amount_out_fallback(amount_in, token_in, token_out, fee_tier)
    
    async def _get_amount_out_fallback(self, amount_in: Decimal, token_in: str, token_out: str, fee_tier: int) -> Decimal:
        """Fallback method using pool price when Quoter fails"""
        try:
            if not self.uniswap_helper:
                return Decimal("0")
                
            # Get pool data using helper
            pool_data = await self.uniswap_helper.get_v3_pool_data(token_in, token_out, fee_tier)
            if not pool_data:
                return Decimal("0")
            
            # Use sqrtPriceX96 for basic price calculation
            sqrt_price_x96 = pool_data.get("sqrtPriceX96", 0)
            if sqrt_price_x96 == 0:
                return Decimal("0")
            
            price = self.uniswap_helper.sqrt_price_to_price(sqrt_price_x96)
            
            # Apply fee (simplified calculation)
            fee_multiplier = 1 - (fee_tier / 1000000)  # fee_tier is in hundredths of a bip
            amount_out = amount_in * price * Decimal(str(fee_multiplier))
            
            return amount_out
            
        except Exception as e:
            logger.error(f"Error in fallback amount calculation: {e}")
            return Decimal("0")
    
    async def get_pool_address(self, token_a: str, token_b: str, fee_tier: int) -> str:
        """Get V3 pool address for tokens and fee tier"""
        try:
            # This would call the factory to compute pool address
            return f"0xabcdef{fee_tier}1234567890abcdef12345678"
            
        except Exception as e:
            logger.error(f"Error getting V3 pool address: {e}")
            return ""
    
    async def get_best_fee_tier(self, token_a: str, token_b: str) -> int:
        """Find the fee tier with the most liquidity"""
        try:
            if not self.uniswap_helper:
                logger.error("UniswapHelper not initialized")
                return 3000
            
            return await self.uniswap_helper.get_best_v3_fee_tier(token_a, token_b)
            
        except Exception as e:
            logger.error(f"Error finding best fee tier: {e}")
            return 3000  # Default
    
    
    async def estimate_gas(self, swap_data: Dict) -> int:
        """Estimate gas for V3 swap transaction"""
        try:
            # V3 swaps typically use more gas than V2 due to complexity
            return 180000
            
        except Exception as e:
            logger.error(f"Error estimating V3 gas: {e}")
            return 200000  # Default estimate