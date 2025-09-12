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
        """Get real exchange rate between two tokens using Jupiter"""
        try:
            # Use real Jupiter API integration
            price = await self.engine.get_token_price_jupiter(token_in, token_out)
            return price
        except Exception as e:
            logger.debug(f"Error getting exchange rate: {e}")
            return None
    
    def _is_stablecoin_pair(self, token_in: str, token_out: str) -> bool:
        """Check if both tokens are stablecoins"""
        stablecoins = [
            self.config.TOKENS["USDC"],
            self.config.TOKENS["USDT"]
        ]
        return token_in in stablecoins and token_out in stablecoins
    
    async def _get_token_price_usd(self, token: str) -> Decimal:
        """Get real token price in USD using Jupiter"""
        try:
            # For stablecoins, return 1.0
            if token in [self.config.TOKENS["USDC"], self.config.TOKENS["USDT"]]:
                return Decimal("1.00")
            
            # Get price against USDC using Jupiter
            usdc_token = self.config.TOKENS["USDC"]
            if token != usdc_token:
                price = await self.engine.get_token_price_jupiter(token, usdc_token)
                if price:
                    return price
            
            # Fallback prices for common tokens
            fallback_prices = {
                self.config.TOKENS["SOL"]: Decimal("180.00"),
                self.config.TOKENS["RAY"]: Decimal("1.50"),
                self.config.TOKENS["ORCA"]: Decimal("4.00"),
                self.config.TOKENS["SRM"]: Decimal("0.60"),
                self.config.TOKENS["BTC"]: Decimal("65000.00"),
                self.config.TOKENS["ETH"]: Decimal("3200.00"),
                self.config.TOKENS["BONK"]: Decimal("0.000025")
            }
            return fallback_prices.get(token, Decimal("1.00"))
            
        except Exception as e:
            logger.debug(f"Error getting USD price for {token}: {e}")
            return Decimal("1.00")
    
    async def _get_sol_price_usd(self) -> Decimal:
        """Get SOL price in USD"""
        try:
            sol_token = self.config.TOKENS["SOL"]
            usdc_token = self.config.TOKENS["USDC"]
            price = await self.engine.get_token_price_jupiter(sol_token, usdc_token)
            return price if price else Decimal("180.00")
        except Exception:
            return Decimal("180.00")  # Fallback
    
    async def _estimate_transaction_cost(self) -> Decimal:
        """Estimate real transaction cost in USD"""
        try:
            # Solana transaction costs are very low
            base_fee_lamports = 5000  # Base transaction fee
            compute_fee_lamports = self.config.PRIORITY_FEE_LAMPORTS
            
            total_fee_lamports = base_fee_lamports + compute_fee_lamports
            total_fee_sol = Decimal(total_fee_lamports) / Decimal(self.config.LAMPORTS_PER_SOL)
            
            # Get SOL price in USD
            sol_price_usd = await self._get_sol_price_usd()
            transaction_cost_usd = total_fee_sol * sol_price_usd
            
            return transaction_cost_usd
            
        except Exception:
            return Decimal("0.01")  # Very low fallback
    
    async def _execute_swap(
        self, 
        token_in: str, 
        token_out: str, 
        amount_in: Decimal
    ) -> Dict[str, Any]:
        """Execute real token swap using Jupiter"""
        try:
            logger.info(f"Executing swap: {amount_in} {token_in} -> {token_out}")
            
            # Convert to lamports/smallest unit
            token_in_decimals = await self.engine._get_token_decimals(token_in)
            amount_in_raw = int(amount_in * Decimal(10 ** token_in_decimals))
            
            # Execute swap using Jupiter
            result = await self.engine.execute_jupiter_swap(
                input_mint=token_in,
                output_mint=token_out,
                amount=amount_in_raw,
                slippage_bps=50  # 0.5% slippage
            )
            
            if result["success"]:
                # Convert output amount back to decimal
                token_out_decimals = await self.engine._get_token_decimals(token_out)
                amount_out = Decimal(result["output_amount"]) / Decimal(10 ** token_out_decimals)
                
                # Estimate transaction cost
                transaction_cost = await self._estimate_transaction_cost()
                
                return {
                    "success": True,
                    "amount_out": amount_out,
                    "tx_signature": result["tx_signature"],
                    "transaction_cost": transaction_cost,
                    "price_impact": result["price_impact"]
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "transaction_cost": Decimal("0")
                }
            
        except Exception as e:
            logger.error(f"Error executing swap: {e}")
            return {
                "success": False,
                "error": str(e),
                "transaction_cost": Decimal("0")
            }
    
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
            
            # Execute the three swaps in sequence
            swap_results = []
            amount_after_first = start_amount
            amount_after_second = start_amount
            
            # First swap
            swap_result = await self._execute_swap(token_a, token_b, amount_after_first)
            swap_results.append(swap_result)
            if swap_result["success"]:
                amount_after_first = swap_result["amount_out"]
            
            # Second swap
            swap_result = await self._execute_swap(token_b, token_c, amount_after_first)
            swap_results.append(swap_result)
            if swap_result["success"]:
                amount_after_second = swap_result["amount_out"]
            
            # Third swap
            swap_result = await self._execute_swap(token_c, token_a, amount_after_second)
            swap_results.append(swap_result)
            
            # Calculate final amount and transaction cost
            final_amount = amount_after_second
            if swap_result["success"]:
                final_amount = swap_result["amount_out"]
            
            total_transaction_cost = sum([swap_result["transaction_cost"] for swap_result in swap_results])
            
            # Return the result
            if all([swap_result["success"] for swap_result in swap_results]):
                return {
                    "success": True,
                    "final_amount": final_amount,
                    "token_price": await self._get_token_price_usd(token_a),
                    "total_transaction_cost": total_transaction_cost,
                    "tx_signatures": [swap_result["tx_signature"] for swap_result in swap_results]
                }
            else:
                return {
                    "success": False,
                    "error": "Swap failed",
                    "total_transaction_cost": total_transaction_cost
                }
            
        except Exception as e:
            logger.error(f"Error executing triangular swaps: {e}")
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