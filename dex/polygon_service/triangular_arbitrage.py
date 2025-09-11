import asyncio
import logging
from decimal import Decimal
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import sys
import os

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from interfaces.base_engine import BaseArbitrageEngine
from models.arbitrage_models import ArbitrageOpportunity, ExecutionResult

from .engine import PolygonEngine
from .config import PolygonConfig

logger = logging.getLogger(__name__)

class PolygonTriangularArbitrageEngine(BaseArbitrageEngine):
    """Polygon Triangular arbitrage engine"""
    
    def __init__(self, engine: PolygonEngine, config: PolygonConfig):
        self.engine = engine
        self.config = config
        self.initialized = False
        
        # Triangular arbitrage paths on Polygon
        self.triangular_paths = [
            # WMATIC -> USDC -> USDT -> WMATIC
            [config.TOKENS["WMATIC"], config.TOKENS["USDC"], config.TOKENS["USDT"]],
            # WMATIC -> USDC -> DAI -> WMATIC
            [config.TOKENS["WMATIC"], config.TOKENS["USDC"], config.TOKENS["DAI"]],
            # WMATIC -> WETH -> USDC -> WMATIC
            [config.TOKENS["WMATIC"], config.TOKENS["WETH"], config.TOKENS["USDC"]],
            # WMATIC -> WBTC -> USDC -> WMATIC
            [config.TOKENS["WMATIC"], config.TOKENS["WBTC"], config.TOKENS["USDC"]],
            # USDC -> USDT -> DAI -> USDC (stablecoin triangle)
            [config.TOKENS["USDC"], config.TOKENS["USDT"], config.TOKENS["DAI"]],
        ]
        
        # Primary DEX for triangular arbitrage (QuickSwap)
        self.primary_dex = {
            "router": config.QUICKSWAP_V2_ROUTER,
            "factory": config.QUICKSWAP_V2_FACTORY,
            "fee": 0.003  # 0.3%
        }
        
    async def initialize(self) -> None:
        """Initialize triangular arbitrage engine"""
        try:
            logger.info("Initializing Polygon Triangular Arbitrage Engine...")
            self.initialized = True
            logger.info("Polygon Triangular Arbitrage Engine initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Polygon triangular arbitrage: {e}")
            raise
    
    async def scan_opportunities(self) -> List[ArbitrageOpportunity]:
        """Scan for triangular arbitrage opportunities on Polygon"""
        if not self.initialized:
            return []
        
        opportunities = []
        
        try:
            for path in self.triangular_paths:
                opportunity = await self._check_triangular_path(path)
                if opportunity:
                    opportunities.append(opportunity)
            
            logger.info(f"Found {len(opportunities)} Polygon triangular arbitrage opportunities")
            return opportunities
            
        except Exception as e:
            logger.error(f"Error scanning Polygon triangular arbitrage: {e}")
            return []
    
    async def execute_opportunity(self, opportunity: ArbitrageOpportunity) -> ExecutionResult:
        """Execute triangular arbitrage on Polygon"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            logger.info(f"Executing Polygon triangular arbitrage: {opportunity.id}")
            
            # Execute the three swaps in sequence
            result = await self._execute_triangular_swaps(
                opportunity.token_a,
                opportunity.token_b, 
                opportunity.token_c,
                opportunity.amount_in
            )
            
            execution_time = asyncio.get_event_loop().time() - start_time
            
            if result["success"]:
                actual_profit = result["final_amount"] - opportunity.amount_in
                
                return ExecutionResult(
                    opportunity_id=opportunity.id,
                    success=True,
                    profit_usd=actual_profit * result["token_price"],  # Convert to USD
                    gas_cost_usd=result["total_gas_cost"],
                    execution_time=execution_time,
                    transaction_hashes=result["tx_hashes"]
                )
            else:
                return ExecutionResult(
                    opportunity_id=opportunity.id,
                    success=False,
                    profit_usd=Decimal("0"),
                    gas_cost_usd=result.get("total_gas_cost", Decimal("0")),
                    execution_time=execution_time,
                    error=result["error"]
                )
                
        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"Polygon triangular arbitrage execution failed: {e}")
            
            return ExecutionResult(
                opportunity_id=opportunity.id,
                success=False,
                profit_usd=Decimal("0"),
                gas_cost_usd=Decimal("0"),
                execution_time=execution_time,
                error=str(e)
            )
    
    async def _check_triangular_path(self, path: List[str]) -> Optional[ArbitrageOpportunity]:
        """Check if a triangular path is profitable"""
        try:
            token_a, token_b, token_c = path
            start_amount = Decimal("1000.0")  # 1000 units of token_a
            
            # Get exchange rates for each step
            rate_ab = await self._get_exchange_rate(token_a, token_b)
            rate_bc = await self._get_exchange_rate(token_b, token_c)
            rate_ca = await self._get_exchange_rate(token_c, token_a)
            
            if not all([rate_ab, rate_bc, rate_ca]):
                return None
            
            # Calculate final amount after complete cycle
            amount_b = start_amount * rate_ab * (1 - Decimal("0.003"))  # Subtract fee
            amount_c = amount_b * rate_bc * (1 - Decimal("0.003"))     # Subtract fee
            final_amount = amount_c * rate_ca * (1 - Decimal("0.003")) # Subtract fee
            
            profit = final_amount - start_amount
            profit_percentage = (profit / start_amount) * 100
            
            if profit_percentage > Decimal(str(self.config.MIN_PROFIT_THRESHOLD)):
                # Calculate profit in USD
                token_a_price_usd = await self._get_token_price_usd(token_a)
                profit_usd = profit * token_a_price_usd
                
                # Check if profit exceeds gas costs
                gas_cost_usd = await self._estimate_triangular_gas_cost()
                
                if profit_usd > gas_cost_usd + Decimal("5"):  # Minimum $5 net profit
                    return ArbitrageOpportunity(
                        id=f"polygon_triangular_{token_a[:8]}_{datetime.now().timestamp()}",
                        type="triangular",
                        chain="polygon",
                        token_a=token_a,
                        token_b=token_b,
                        token_c=token_c,
                        exchange_a="quickswap",
                        price_a=rate_ab,
                        price_b=rate_bc,
                        price_c=rate_ca,
                        price_difference=profit_percentage,
                        profit_usd=profit_usd,
                        gas_cost_usd=gas_cost_usd,
                        amount_in=start_amount,
                        amount_out=final_amount,
                        amount_ab=amount_b,
                        amount_bc=amount_c,
                        total_liquidity_usd=await self._estimate_path_liquidity(path),
                        price_impact=await self._estimate_triangular_price_impact(start_amount, path),
                        timestamp=datetime.now()
                    )
            
            return None
            
        except Exception as e:
            logger.debug(f"Error checking triangular path: {e}")
            return None
    
    async def _get_exchange_rate(self, token_in: str, token_out: str) -> Optional[Decimal]:
        """Get exchange rate between two tokens"""
        try:
            # Mock rates based on token types
            if self._is_stablecoin(token_in) and self._is_stablecoin(token_out):
                return Decimal("1.002")  # Slight premium for stablecoin swaps
            elif token_in == self.config.TOKENS["WMATIC"]:
                if token_out == self.config.TOKENS["USDC"]:
                    return Decimal("0.85")    # WMATIC/USDC rate
                elif token_out == self.config.TOKENS["WETH"]:
                    return Decimal("0.00026") # WMATIC/WETH rate
                elif token_out == self.config.TOKENS["WBTC"]:
                    return Decimal("0.000013") # WMATIC/WBTC rate
            elif token_out == self.config.TOKENS["WMATIC"]:
                # Inverse rates
                rate = await self._get_exchange_rate(token_out, token_in)
                return Decimal("1") / rate if rate else None
            
            # Default fallback rate
            return Decimal("1.0")
            
        except Exception as e:
            logger.debug(f"Error getting exchange rate {token_in}/{token_out}: {e}")
            return None
    
    def _is_stablecoin(self, token: str) -> bool:
        """Check if token is a stablecoin"""
        stablecoins = [
            self.config.TOKENS["USDC"],
            self.config.TOKENS["USDT"],
            self.config.TOKENS["DAI"]
        ]
        return token in stablecoins
    
    async def _get_token_price_usd(self, token: str) -> Decimal:
        """Get token price in USD"""
        try:
            # Mock USD prices
            if token == self.config.TOKENS["WMATIC"]:
                return Decimal("0.85")
            elif self._is_stablecoin(token):
                return Decimal("1.00")
            elif token == self.config.TOKENS["WETH"]:
                return Decimal("3200.00")
            elif token == self.config.TOKENS["WBTC"]:
                return Decimal("65000.00")
            else:
                return Decimal("1.00")  # Fallback
                
        except Exception:
            return Decimal("1.00")
    
    async def _estimate_triangular_gas_cost(self) -> Decimal:
        """Estimate gas cost for triangular arbitrage"""
        try:
            # Polygon gas cost for 3 swaps
            gas_price_gwei = 30
            gas_used = 300000  # Three swaps
            
            matic_price_usd = Decimal("0.85")
            
            gas_cost_matic = Decimal(str(gas_price_gwei)) * Decimal(str(gas_used)) / Decimal("1e9")
            gas_cost_usd = gas_cost_matic * matic_price_usd
            
            return gas_cost_usd
            
        except Exception:
            return Decimal("0.75")  # Fallback - very low on Polygon
    
    async def _estimate_path_liquidity(self, path: List[str]) -> Decimal:
        """Estimate liquidity for triangular path"""
        return Decimal("300000")  # $300K mock liquidity
    
    async def _estimate_triangular_price_impact(self, amount: Decimal, path: List[str]) -> float:
        """Estimate price impact for triangular arbitrage"""
        return 0.12  # 0.12%
    
    async def _execute_triangular_swaps(
        self, 
        token_a: str, 
        token_b: str, 
        token_c: str, 
        start_amount: Decimal
    ) -> Dict[str, Any]:
        """Execute the three swaps for triangular arbitrage"""
        try:
            logger.info(f"Executing triangular swaps: {token_a} -> {token_b} -> {token_c} -> {token_a}")
            
            # Mock execution
            # Simulate the three swaps
            amount_after_first = start_amount * Decimal("0.997")   # After fees
            amount_after_second = amount_after_first * Decimal("0.997")
            final_amount = amount_after_second * Decimal("1.005")  # Profitable final swap
            
            return {
                "success": True,
                "final_amount": final_amount,
                "token_price": await self._get_token_price_usd(token_a),
                "total_gas_cost": Decimal("0.75"),
                "tx_hashes": [
                    f"0x{'poly_swap1' * 9}",
                    f"0x{'poly_swap2' * 9}",
                    f"0x{'poly_swap3' * 9}"
                ]
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "total_gas_cost": Decimal("0")
            }
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get engine health status"""
        return {
            "status": "healthy" if self.initialized else "uninitialized",
            "initialized": self.initialized,
            "triangular_paths": len(self.triangular_paths),
            "primary_dex": "quickswap"
        }