from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Tuple
from decimal import Decimal
import asyncio
import logging

# Import shared models
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from dex.shared.models.arbitrage_models import Token, DexPair, SwapQuote

logger = logging.getLogger(__name__)

class BaseProtocolAdapter(ABC):
    """Base class for Polygon DEX protocol adapters"""
    
    def __init__(self, engine, config):
        self.engine = engine
        self.config = config
        self.protocol_name = ""
        self.router_address = ""
        self.factory_address = ""
        self.fee_rate = Decimal("0")
        
    @abstractmethod
    async def get_pair_address(self, token0: str, token1: str) -> Optional[str]:
        """Get pair address for two tokens"""
        pass
    
    @abstractmethod
    async def get_reserves(self, pair_address: str) -> Tuple[Decimal, Decimal]:
        """Get reserves for a trading pair"""
        pass
    
    @abstractmethod
    async def get_quote(self, amount_in: Decimal, token_in: str, token_out: str) -> SwapQuote:
        """Get quote for a swap"""
        pass
    
    @abstractmethod
    async def execute_swap(self, amount_in: Decimal, min_amount_out: Decimal, 
                          token_in: str, token_out: str, to_address: str) -> Dict[str, Any]:
        """Execute a swap transaction"""
        pass
    
    @abstractmethod
    async def get_liquidity_info(self, token0: str, token1: str) -> Dict[str, Any]:
        """Get liquidity information for a token pair"""
        pass
    
    async def is_pair_exists(self, token0: str, token1: str) -> bool:
        """Check if a trading pair exists"""
        try:
            pair_address = await self.get_pair_address(token0, token1)
            return pair_address is not None and pair_address != "0x0000000000000000000000000000000000000000"
        except Exception as e:
            logger.error(f"Error checking pair existence: {e}")
            return False
    
    async def get_price_impact(self, amount_in: Decimal, token_in: str, token_out: str) -> Decimal:
        """Calculate price impact for a swap"""
        try:
            pair_address = await self.get_pair_address(token_in, token_out)
            if not pair_address:
                return Decimal("100")  # 100% impact if no pair
            
            reserve0, reserve1 = await self.get_reserves(pair_address)
            if reserve0 == 0 or reserve1 == 0:
                return Decimal("100")
            
            # Calculate price impact based on constant product formula
            # This is a simplified calculation
            if token_in.lower() < token_out.lower():
                reserve_in, reserve_out = reserve0, reserve1
            else:
                reserve_in, reserve_out = reserve1, reserve0
            
            # Price impact = (amount_in / (reserve_in + amount_in)) * 100
            price_impact = (amount_in / (reserve_in + amount_in)) * Decimal("100")
            return price_impact
            
        except Exception as e:
            logger.error(f"Error calculating price impact: {e}")
            return Decimal("100")
    
    def get_protocol_info(self) -> Dict[str, Any]:
        """Get protocol information"""
        return {
            "name": self.protocol_name,
            "router_address": self.router_address,
            "factory_address": self.factory_address,
            "fee_rate": float(self.fee_rate)
        }
