from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from decimal import Decimal

class BaseEngine(ABC):
    """Base interface for all chain engines"""
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize Web3 connection and contracts"""
        pass
    
    @abstractmethod
    async def get_balance(self, token_address: str, wallet_address: str) -> Decimal:
        """Get token balance for wallet"""
        pass
    
    @abstractmethod
    async def get_gas_price(self) -> int:
        """Get current gas price"""
        pass
    
    @abstractmethod
    async def execute_transaction(self, tx_data: Dict[str, Any]) -> str:
        """Execute transaction and return tx hash"""
        pass

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