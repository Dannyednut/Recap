from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple

from .base_engine import BaseEngine

class BaseArbitrageStrategy(ABC):
    """Base class for arbitrage strategy implementations"""
    
    def __init__(self, engine: BaseEngine, config: Dict[str, Any]):
        """Initialize the arbitrage strategy"""
        self.engine = engine
        self.config = config
        self.is_running = False
        self.min_profit_threshold = config.get('min_profit_threshold', 0.001)  # 0.1% default
        self.use_flashloan = config.get('use_flashloan', True)
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the strategy with necessary connections and configurations"""
        pass
    
    @abstractmethod
    async def scan_opportunities(self) -> List[Dict[str, Any]]:
        """Scan for arbitrage opportunities"""
        pass
    
    @abstractmethod
    async def calculate_profit(self, opportunity: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """Calculate potential profit for an opportunity"""
        pass
    
    @abstractmethod
    async def execute_arbitrage(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an arbitrage opportunity"""
        pass
    
    @abstractmethod
    async def start(self) -> bool:
        """Start the arbitrage strategy"""
        self.is_running = True
        return True
    
    @abstractmethod
    async def stop(self) -> bool:
        """Stop the arbitrage strategy"""
        self.is_running = False
        return True
    
    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the strategy's performance"""
        pass
    
    @abstractmethod
    async def estimate_gas_cost(self, opportunity: Dict[str, Any]) -> int:
        """Estimate gas cost for executing an opportunity"""
        pass
    
    @abstractmethod
    async def validate_opportunity(self, opportunity: Dict[str, Any]) -> bool:
        """Validate if an opportunity is still valid"""
        pass
    
    @abstractmethod
    async def simulate_execution(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate execution of an opportunity without actually executing it"""
        pass
    
    @abstractmethod
    async def get_required_tokens(self, opportunity: Dict[str, Any]) -> List[str]:
        """Get the list of tokens required for an opportunity"""
        pass
    
    @abstractmethod
    async def get_required_amount(self, opportunity: Dict[str, Any]) -> int:
        """Get the required amount of tokens for an opportunity"""
        pass
    
    @abstractmethod
    async def prepare_flashloan_params(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare parameters for a flashloan"""
        pass