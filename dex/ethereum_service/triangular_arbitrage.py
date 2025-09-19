import asyncio
import logging
import time
from decimal import Decimal
from typing import List, Dict, Any, Optional
import sys
import os

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from interfaces.base_engine import BaseArbitrageStrategy
from models.arbitrage_models import ArbitrageOpportunity, Token, ExecutionResult

from .engine import EthereumEngine
from .config import EthereumConfig

logger = logging.getLogger(__name__)

class TriangularArbitrageEngine(BaseArbitrageStrategy):
    """Triangular arbitrage within same DEX (e.g., ETH->USDC->DAI->ETH on Uniswap)"""
    
    def __init__(self, engine: EthereumEngine, config: EthereumConfig):
        self.engine = engine
        self.config = config
        self.triangular_paths = []
        
    async def initialize(self):
        """Initialize triangular arbitrage paths"""
        logger.info("Initializing Ethereum triangular arbitrage engine...")
        self.triangular_paths = self._generate_triangular_paths()
        
    async def scan_opportunities(self) -> List[ArbitrageOpportunity]:
        """Scan for triangular arbitrage opportunities"""
        opportunities = []
        
        try:
            for path in self.triangular_paths:
                opportunity = await self._analyze_triangular_path(path)
                if opportunity:
                    opportunities.append(opportunity)
                    
        except Exception as e:
            logger.error(f"Error scanning triangular opportunities: {e}")
        
        return opportunities
    
    async def calculate_profit(self, opportunity: ArbitrageOpportunity) -> Decimal:
        """Calculate triangular arbitrage profit"""
        try:
            # Simulate the triangular trade path
            if not opportunity.tokens_path or len(opportunity.tokens_path) != 3:
                return Decimal("0")
            
            # Start with base amount
            amount = Decimal(str(self.config.MAX_TRADE_SIZE_ETH))
            
            # Simulate each hop in the triangular path
            for i in range(len(opportunity.tokens_path) - 1):
                token_from = opportunity.tokens_path[i]
                token_to = opportunity.tokens_path[i + 1]
                
                # Get exchange rate (simplified)
                rate = await self._get_exchange_rate(token_from, token_to)
                amount = amount * rate
            
            # Calculate profit
            initial_amount = Decimal(str(self.config.MAX_TRADE_SIZE_ETH))
            profit = amount - initial_amount
            
            # Subtract gas costs
            gas_cost = await self._estimate_triangular_gas_cost()
            net_profit = profit - gas_cost
            
            return net_profit
            
        except Exception as e:
            logger.error(f"Error calculating triangular profit: {e}")
            return Decimal("0")
    
    async def execute_opportunity(self, opportunity: ArbitrageOpportunity) -> ExecutionResult:
        """Execute triangular arbitrage opportunity using real DEX contracts"""
        start_time = time.time()
        
        try:
            logger.info(f"Executing Ethereum triangular arbitrage: {opportunity.id}")
            
            # Parse triangular path from opportunity
            path = getattr(opportunity, 'path', ['WETH', 'USDC', 'DAI'])
            amount_in = opportunity.amount_in
            
            # Execute three sequential swaps
            current_amount = amount_in
            tx_hashes = []
            total_gas_cost = Decimal("0")
            
            for i in range(len(path)):
                token_in = path[i]
                token_out = path[(i + 1) % len(path)]  # Circular path
                
                swap_result = await self._execute_triangular_swap(
                    token_in, token_out, current_amount, i + 1
                )
                
                if not swap_result["success"]:
                    raise Exception(f"Swap {i+1} failed: {swap_result['error']}")
                
                current_amount = swap_result["amount_out"]
                tx_hashes.append(swap_result["tx_hash"])
                total_gas_cost += swap_result["gas_cost"]
            
            execution_time = time.time() - start_time
            
            # Calculate actual profit (final amount - initial amount)
            actual_profit = current_amount - amount_in
            
            return ExecutionResult(
                opportunity_id=opportunity.id,
                success=True,
                profit_usd=float(actual_profit * getattr(opportunity, 'price_a', Decimal("1"))),
                gas_cost_usd=float(total_gas_cost),
                execution_time=execution_time,
                transaction_hashes=tx_hashes
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Ethereum triangular arbitrage execution failed: {e}")
            
            return ExecutionResult(
                opportunity_id=opportunity.id,
                success=False,
                profit_usd=0.0,
                gas_cost_usd=0.0,
                execution_time=execution_time,
                error=str(e)
            )
    
    async def _execute_triangular_swap(
        self, 
        token_in: str, 
        token_out: str, 
        amount_in: Decimal,
        swap_number: int
    ) -> Dict[str, Any]:
        """Execute a single swap in the triangular arbitrage sequence"""
        try:
            logger.info(f"Executing triangular swap {swap_number}: {amount_in} {token_in} -> {token_out}")
            
            # Use Uniswap V2 for triangular arbitrage (more predictable)
            tx_hash = await self.uniswap_v2.execute_swap(
                token_in, token_out, int(amount_in * Decimal(10**18))
            )
            
            if not tx_hash:
                return {
                    "success": False,
                    "error": "Failed to execute swap",
                    "gas_cost": Decimal("0")
                }
            
            # Wait for confirmation
            result = await self.engine.wait_for_transaction_receipt(tx_hash)
            
            if result:
                # Calculate output amount (simplified estimation)
                fee_rate = Decimal("0.003")  # 0.3% Uniswap fee
                amount_out = amount_in * (Decimal("1") - fee_rate)
                gas_cost_usd = await self._estimate_gas_cost_usd(result.gasUsed)
                
                return {
                    "success": True,
                    "amount_out": amount_out,
                    "tx_hash": tx_hash.hex(),
                    "gas_cost": gas_cost_usd
                }
            else:
                return {
                    "success": False,
                    "error": "Transaction failed",
                    "gas_cost": Decimal("0")
                }
            
        except Exception as e:
            logger.error(f"Error executing triangular swap {swap_number}: {e}")
            return {
                "success": False,
                "error": str(e),
                "gas_cost": Decimal("0")
            }
    
    async def _estimate_gas_cost_usd(self, gas_used: int) -> Decimal:
        """Estimate gas cost in USD using real ETH price"""
        try:
            # Get current gas price
            gas_price = await self.engine.get_gas_price()
            
            # Calculate gas cost in ETH
            gas_cost_eth = Decimal(gas_used * gas_price) / Decimal(10**18)
            
            # Get real ETH price in USD from DEX contracts
            eth_price_usd = await self._get_eth_price_usd()
            
            return gas_cost_eth * eth_price_usd
            
        except Exception as e:
            logger.debug(f"Error estimating gas cost: {e}")
            return Decimal("50")  # Fallback to $50 gas cost
    
    async def _get_eth_price_usd(self) -> Decimal:
        """Get real ETH price in USD from DEX contracts"""
        try:
            # Use the shared price fetcher for real-time ETH price
            from ..shared.price_fetcher import MultiChainPriceFetcher
            price_fetcher = MultiChainPriceFetcher()
            await price_fetcher.initialize()
            
            # Get WETH address for Ethereum
            weth_address = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
            eth_price = await price_fetcher.get_token_price_usd('ethereum', weth_address, self.engine)
            
            await price_fetcher.cleanup()
            return eth_price
            
        except Exception as e:
            logger.debug(f"Error getting real ETH price: {e}")
            return Decimal("3200.00")  # Fallback price
    
    def _generate_triangular_paths(self) -> List[List[str]]:
        """Generate profitable triangular arbitrage paths"""
        paths = []
        
        # Common triangular paths on Ethereum
        paths.extend([
            ["WETH", "USDC", "DAI"],      # ETH -> USDC -> DAI -> ETH
            ["WETH", "USDT", "DAI"],      # ETH -> USDT -> DAI -> ETH
            ["WETH", "WBTC", "USDC"],     # ETH -> WBTC -> USDC -> ETH
            ["USDC", "USDT", "DAI"],      # USDC -> USDT -> DAI -> USDC
            ["WETH", "DAI", "USDT"],      # ETH -> DAI -> USDT -> ETH
        ])
        
        return paths
    
    async def _analyze_triangular_path(self, path: List[str]) -> Optional[ArbitrageOpportunity]:
        """Analyze a triangular path for arbitrage opportunity"""
        try:
            # Calculate the effective exchange rate for the full path
            effective_rate = Decimal("1")
            
            for i in range(len(path)):
                token_from = path[i]
                token_to = path[(i + 1) % len(path)]  # Wrap around to close the triangle
                
                rate = await self._get_exchange_rate(token_from, token_to)
                effective_rate *= rate
            
            # Check if completing the triangle results in profit
            profit_pct = (effective_rate - 1) * 100
            
            if profit_pct < self.config.MIN_PROFIT_THRESHOLD:
                return None
            
            # Create tokens for the path
            tokens = [Token(
                address=self.config.TOKENS.get(symbol, "0x0"),
                symbol=symbol,
                decimals=18,
                name=symbol
            ) for symbol in path]
            
            return ArbitrageOpportunity(
                opportunity_id=f"triangular_{'_'.join(path)}_{int(datetime.now().timestamp())}",
                strategy_type="triangular",
                chain="ethereum",
                profit_percentage=profit_pct,
                profit_amount_usd=Decimal("0"),  # Will be calculated later
                gas_cost_usd=Decimal("0"),      # Will be calculated later
                net_profit_usd=Decimal("0"),    # Will be calculated later
                detected_at=datetime.now(),
                tokens_path=tokens
            )
            
        except Exception as e:
            logger.error(f"Error analyzing triangular path {path}: {e}")
            return None
    
    async def _get_exchange_rate(self, token_from: str, token_to: str) -> Decimal:
        """Get exchange rate between two tokens (simplified)"""
        # Placeholder implementation with mock rates
        rates = {
            ("WETH", "USDC"): Decimal("1800"),
            ("USDC", "DAI"): Decimal("1.001"),
            ("DAI", "WETH"): Decimal("0.000555"),
            ("WETH", "USDT"): Decimal("1799"),
            ("USDT", "DAI"): Decimal("0.9995"),
            ("WETH", "WBTC"): Decimal("0.045"),
            ("WBTC", "USDC"): Decimal("40000"),
        }
        
        # Try direct rate
        direct_rate = rates.get((token_from, token_to))
        if direct_rate:
            return direct_rate
        
        # Try inverse rate
        inverse_rate = rates.get((token_to, token_from))
        if inverse_rate:
            return Decimal("1") / inverse_rate
        
        # Default rate
        return Decimal("1")
    
    async def _estimate_triangular_gas_cost(self) -> Decimal:
        """Estimate gas cost for triangular arbitrage"""
        try:
            # Estimate for flash loan + 3 swaps
            estimated_gas = 350000
            gas_price = await self.engine.get_gas_price()
            
            # Convert to USD (simplified)
            eth_price_usd = Decimal("1800")
            gas_cost_eth = Decimal(str(estimated_gas * gas_price)) / Decimal("1e18")
            gas_cost_usd = gas_cost_eth * eth_price_usd
            
            return gas_cost_usd
            
        except Exception as e:
            logger.error(f"Error estimating triangular gas cost: {e}")
            return Decimal("40")  # Default $40 estimate