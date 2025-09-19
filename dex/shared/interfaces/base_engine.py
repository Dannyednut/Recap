from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from decimal import Decimal

class BaseArbitrageStrategy(ABC):
    """Base interface for arbitrage strategies"""
    
    @abstractmethod
    async def scan_opportunities(self) -> List[Dict[str, Any]]:
        """Scan for arbitrage opportunities - returns List[ArbitrageOpportunity]"""
        pass
    
    @abstractmethod
    async def calculate_profit(self, opportunity: Dict[str, Any]) -> Decimal:
        """Calculate potential profit for ArbitrageOpportunity"""
        pass
    
    @abstractmethod
    async def execute_arbitrage(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Execute arbitrage with flashloan"""
        pass

# Alias for backward compatibility
BaseArbitrageEngine = BaseArbitrageStrategy

# Import BaseEngine - using try/except to handle import issues gracefully
try:
    from ..base_engine import BaseEngine
except ImportError:
    # Fallback for when running as standalone module
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    try:
        from base_engine import BaseEngine
    except ImportError:
        # Create a minimal BaseEngine if not available
        class BaseEngine:
            pass

class BaseProtocolAdapter(ABC):
    """Base interface for DEX protocol adapters"""
    
    @abstractmethod
    async def get_pair_price(self, token_a: str, token_b: str) -> Decimal:
        """Get pair price from DEX"""
        pass
    
    @abstractmethod
    async def get_liquidity(self, pair_address: str) -> Decimal:
        """Get pair liquidity"""
        pass
    
    @abstractmethod
    async def build_swap_data(self, token_in: str, token_out: str, amount: Decimal) -> Dict:
        """Build swap transaction data"""
        pass