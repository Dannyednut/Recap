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


from .engine import SolanaEngine
from .config import SolanaConfig

logger = logging.getLogger(__name__)

class SolanaTriangularArbitrageEngine(BaseArbitrageEngine):
    """Solana Triangular arbitrage engine"""
    
    def __init__(self, engine: SolanaEngine, config: SolanaConfig):
        self.engine = engine
        self.config = config
        self.initialized = False
        
        # Triangular arbitrage paths on Solana
        self.triangular_paths = [
            # SOL -> USDC -> USDT -> SOL
            [config.TOKENS["SOL"], config.TOKENS["USDC"], config.TOKENS["USDT"]],
            # SOL -> RAY -> USDC -> SOL
            [config.TOKENS["SOL"], config.TOKENS["RAY"], config.TOKENS["USDC"]],
            # SOL -> ORCA -> USDC -> SOL
            [config.TOKENS["SOL"], config.TOKENS["ORCA"], config.TOKENS["USDC"]],
            # SOL -> SRM -> USDC -> SOL
            [config.TOKENS["SOL"], config.TOKENS["SRM"], config.TOKENS["USDC"]],
            # USDC -> USDT -> RAY -> USDC (involving stablecoins)
            [config.TOKENS["USDC"], config.TOKENS["USDT"], config.TOKENS["RAY"]],
        ]
        
        # Primary DEX for triangular arbitrage (Jupiter for routing)
        self.primary_dex = {
            "program_id": config.JUPITER_V6,
            "type": "aggregator"
        }
        
    async def initialize(self) -> None:
        """Initialize triangular arbitrage engine"""
        try:
            logger.info("Initializing Solana Triangular Arbitrage Engine...")
            self.initialized = True
            logger.info("Solana Triangular Arbitrage Engine initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Solana triangular arbitrage: {e}")
            raise
    
    async def scan_opportunities(self) -> List[ArbitrageOpportunity]:
        """Scan for triangular arbitrage opportunities on Solana"""
        if not self.initialized:
            return []
        
        opportunities = []
        
        try:
            for path in self.triangular_paths:
                opportunity = await self._check_triangular_path(path)
                if opportunity:
                    opportunities.append(opportunity)
            
            logger.info(f"Found {len(opportunities)} Solana triangular arbitrage opportunities")
            return opportunities
            
        except Exception as e:
            logger.error(f"Error scanning Solana triangular arbitrage: {e}")
            return []
    
    async def execute_opportunity(self, opportunity: ArbitrageOpportunity) -> ExecutionResult:
        """Execute triangular arbitrage on Solana"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            logger.info(f"Executing Solana triangular arbitrage: {opportunity.id}")
            
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
                    gas_cost_usd=result["total_transaction_cost"],
                    execution_time=execution_time,
                    transaction_hashes=result["tx_signatures"]
                )
            else:
                return ExecutionResult(
                    opportunity_id=opportunity.id,
                    success=False,
                    profit_usd=Decimal("0"),
                    gas_cost_usd=result.get("total_transaction_cost", Decimal("0")),
                    execution_time=execution_time,
                    error=result["error"]
                )
                
        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"Solana triangular arbitrage execution failed: {e}")
            
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
            start_amount = Decimal("100.0")  # 100 units of token_a
            
            # Get exchange rates for each step
            rate_ab = await self._get_exchange_rate(token_a, token_b)
            rate_bc = await self._get_exchange_rate(token_b, token_c)
            rate_ca = await self._get_exchange_rate(token_c, token_a)
            
            if not all([rate_ab, rate_bc, rate_ca]):
                return None
            
            # Calculate final amount after complete cycle (including fees)
            fee_rate = Decimal("0.0025")  # Average fee across DEXes
            amount_b = start_amount * rate_ab * (1 - fee_rate)  # Subtract fee
            amount_c = amount_b * rate_bc * (1 - fee_rate)       # Subtract fee
            final_amount = amount_c * rate_ca * (1 - fee_rate)   # Subtract fee
            
            profit = final_amount - start_amount
            profit_percentage = (profit / start_amount) * 100
            
            if profit_percentage > Decimal(str(self.config.MIN_PROFIT_THRESHOLD)):
                # Calculate profit in USD
                token_a_price_usd = await self._get_token_price_usd(token_a)
                profit_usd = profit * token_a_price_usd
                
                # Check if profit exceeds transaction costs
                transaction_cost_usd = await self._estimate_triangular_transaction_cost()
                
                if profit_usd > transaction_cost_usd + Decimal("3"):  # Minimum $3 net profit
                    return ArbitrageOpportunity(
                        id=f"solana_triangular_{token_a[:8]}_{datetime.now().timestamp()}",
                        type="triangular",
                        chain="solana",
                        token_a=token_a,
                        token_b=token_b,
                        token_c=token_c,
                        exchange_a="jupiter",
                        price_a=rate_ab,
                        price_b=rate_bc,
                        price_c=rate_ca,
                        price_difference=profit_percentage,
                        profit_usd=profit_usd,
                        gas_cost_usd=transaction_cost_usd,
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
            # Use Jupiter aggregator for best rates
            if token_in == self.config.TOKENS["SOL"]:
                if token_out == self.config.TOKENS["USDC"]:
                    return Decimal("180.25")  # SOL/USDC rate
                elif token_out == self.config.TOKENS["RAY"]:
                    return Decimal("120.0")   # SOL/RAY rate
                elif token_out == self.config.TOKENS["ORCA"]:
                    return Decimal("45.0")    # SOL/ORCA rate
                elif token_out == self.config.TOKENS["SRM"]:
                    return Decimal("300.0")   # SOL/SRM rate
            elif token_out == self.config.TOKENS["SOL"]:
                # Inverse rates
                rate = await self._get_exchange_rate(token_out, token_in)
                return Decimal("1") / rate if rate else None
            elif self._is_stablecoin_pair(token_in, token_out):
                return Decimal("1.002")  # Slight premium for stablecoin swaps
            elif token_in == self.config.TOKENS["RAY"] and token_out == self.config.TOKENS["USDC"]:
                return Decimal("1.48")  # RAY/USDC
            elif token_in == self.config.TOKENS["ORCA"] and token_out == self.config.TOKENS["USDC"]:
                return Decimal("3.95")  # ORCA/USDC
            
            # Default fallback rate
            return Decimal("1.0")
            
        except Exception as e:
            logger.debug(f"Error getting exchange rate {token_in}/{token_out}: {e}")
            return None
    
    def _is_stablecoin_pair(self, token_in: str, token_out: str) -> bool:
        """Check if both tokens are stablecoins"""
        stablecoins = [
            self.config.TOKENS["USDC"],
            self.config.TOKENS["USDT"]
        ]
        return token_in in stablecoins and token_out in stablecoins
    
    async def _get_token_price_usd(self, token: str) -> Decimal:
        """Get token price in USD"""
        try:
            # Mock USD prices for Solana tokens
            if token == self.config.TOKENS["SOL"]:
                return Decimal("180.00")
            elif token == self.config.TOKENS["USDC"]:
                return Decimal("1.00")
            elif token == self.config.TOKENS["USDT"]:
                return Decimal("1.00")
            elif token == self.config.TOKENS["RAY"]:
                return Decimal("1.50")
            elif token == self.config.TOKENS["ORCA"]:
                return Decimal("4.00")
            elif token == self.config.TOKENS["SRM"]:
                return Decimal("0.60")
            else:
                return Decimal("1.00")  # Fallback
                
        except Exception:
            return Decimal("1.00")
    
    async def _estimate_triangular_transaction_cost(self) -> Decimal:
        """Estimate transaction cost for triangular arbitrage"""
        try:
            # Solana transaction cost for 3 swaps (could be batched)
            base_fee_lamports = 5000  # Base transaction fee
            compute_fee_lamports = self.config.PRIORITY_FEE_LAMPORTS * 3  # 3 swaps
            
            total_fee_lamports = base_fee_lamports + compute_fee_lamports
            total_fee_sol = Decimal(total_fee_lamports) / Decimal(self.config.LAMPORTS_PER_SOL)
            
            sol_price_usd = Decimal("180.00")
            transaction_cost_usd = total_fee_sol * sol_price_usd
            
            return transaction_cost_usd
            
        except Exception:
            return Decimal("0.02")  # Very low fallback
    
    async def _estimate_path_liquidity(self, path: List[str]) -> Decimal:
        """Estimate liquidity for triangular path"""
        return Decimal("1000000")  # $1M mock liquidity
    
    async def _estimate_triangular_price_impact(self, amount: Decimal, path: List[str]) -> float:
        """Estimate price impact for triangular arbitrage"""
        return 0.08  # 0.08%
    
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
            
            # Mock execution using Jupiter aggregator
            # This could be done as a single batched transaction on Solana
            
            # Simulate the three swaps
            amount_after_first = start_amount * Decimal("0.9975")   # After fees
            amount_after_second = amount_after_first * Decimal("0.9975")
            final_amount = amount_after_second * Decimal("1.008")  # Profitable final swap
            
            return {
                "success": True,
                "final_amount": final_amount,
                "token_price": await self._get_token_price_usd(token_a),
                "total_transaction_cost": Decimal("0.015"),  # Very low on Solana
                "tx_signatures": [
                    f"{'sol_tri_1' * 8}{'1' * 24}",
                    f"{'sol_tri_2' * 8}{'2' * 24}",
                    f"{'sol_tri_3' * 8}{'3' * 24}"
                ]
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "total_transaction_cost": Decimal("0")
            }
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get engine health status"""
        return {
            "status": "healthy" if self.initialized else "uninitialized",
            "initialized": self.initialized,
            "triangular_paths": len(self.triangular_paths),
            "primary_dex": "jupiter"
        }