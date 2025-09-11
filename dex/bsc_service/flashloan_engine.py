import asyncio
import logging
from decimal import Decimal
from typing import Dict, List, Any, Optional
from datetime import datetime
import sys
import os

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from interfaces.base_engine import BaseArbitrageEngine
from models.arbitrage_models import ArbitrageOpportunity, ExecutionResult

from .engine import BSCEngine
from .config import BSCConfig

logger = logging.getLogger(__name__)

class BSCFlashLoanEngine(BaseArbitrageEngine):
    """BSC Flash loan arbitrage engine"""
    
    def __init__(self, engine: BSCEngine, config: BSCConfig):
        self.engine = engine
        self.config = config
        self.initialized = False
        
        # Flash loan providers on BSC
        self.flash_loan_providers = {
            "venus": {
                "address": config.VENUS_COMPTROLLER,
                "fee": 0.0009,  # 0.09%
                "max_amount": {
                    config.TOKENS["WBNB"]: Decimal("10000"),
                    config.TOKENS["BUSD"]: Decimal("5000000"),
                    config.TOKENS["USDT"]: Decimal("5000000"),
                    config.TOKENS["USDC"]: Decimal("5000000"),
                    config.TOKENS["ETH"]: Decimal("1000"),
                    config.TOKENS["BTCB"]: Decimal("100")
                }
            },
            "alpaca": {
                "address": config.ALPACA_LENDING_POOL,
                "fee": 0.0005,  # 0.05%
                "max_amount": {
                    config.TOKENS["WBNB"]: Decimal("5000"),
                    config.TOKENS["BUSD"]: Decimal("2000000"),
                    config.TOKENS["USDT"]: Decimal("2000000")
                }
            }
        }
        
        # DEX combinations for flash loan arbitrage
        self.dex_combinations = [
            ("pancakeswap_v2", "biswap"),
            ("pancakeswap_v2", "apeswap"),
            ("biswap", "apeswap"),
            ("pancakeswap_v3", "pancakeswap_v2")
        ]
        
    async def initialize(self) -> None:
        """Initialize flash loan engine"""
        try:
            logger.info("Initializing BSC Flash Loan Engine...")
            self.initialized = True
            logger.info("BSC Flash Loan Engine initialized")
        except Exception as e:
            logger.error(f"Failed to initialize BSC flash loan engine: {e}")
            raise
    
    async def scan_opportunities(self) -> List[ArbitrageOpportunity]:
        """Scan for flash loan arbitrage opportunities on BSC"""
        if not self.initialized:
            return []
        
        opportunities = []
        
        try:
            # Check major token pairs for flash loan opportunities
            major_tokens = [
                self.config.TOKENS["WBNB"],
                self.config.TOKENS["BUSD"],
                self.config.TOKENS["USDT"],
                self.config.TOKENS["USDC"],
                self.config.TOKENS["ETH"]
            ]
            
            for i, token_a in enumerate(major_tokens):
                for token_b in major_tokens[i+1:]:
                    for dex_a, dex_b in self.dex_combinations:
                        opportunity = await self._check_flash_loan_opportunity(
                            token_a, token_b, dex_a, dex_b
                        )
                        if opportunity:
                            opportunities.append(opportunity)
            
            logger.info(f"Found {len(opportunities)} BSC flash loan opportunities")
            return opportunities
            
        except Exception as e:
            logger.error(f"Error scanning BSC flash loan opportunities: {e}")
            return []
    
    async def execute_opportunity(self, opportunity: ArbitrageOpportunity) -> ExecutionResult:
        """Execute flash loan arbitrage on BSC"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            logger.info(f"Executing BSC flash loan arbitrage: {opportunity.id}")
            
            # Select best flash loan provider
            provider = await self._select_best_provider(
                opportunity.token_a, 
                opportunity.loan_amount
            )
            
            if not provider:
                raise Exception("No suitable flash loan provider found")
            
            # Execute flash loan arbitrage
            result = await self._execute_flash_loan_arbitrage(
                provider,
                opportunity
            )
            
            execution_time = asyncio.get_event_loop().time() - start_time
            
            if result["success"]:
                return ExecutionResult(
                    opportunity_id=opportunity.id,
                    success=True,
                    profit_usd=result["profit_usd"],
                    gas_cost_usd=result["gas_cost_usd"],
                    execution_time=execution_time,
                    transaction_hashes=[result["tx_hash"]]
                )
            else:
                return ExecutionResult(
                    opportunity_id=opportunity.id,
                    success=False,
                    profit_usd=Decimal("0"),
                    gas_cost_usd=result.get("gas_cost_usd", Decimal("0")),
                    execution_time=execution_time,
                    error=result["error"]
                )
                
        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"BSC flash loan execution failed: {e}")
            
            return ExecutionResult(
                opportunity_id=opportunity.id,
                success=False,
                profit_usd=Decimal("0"),
                gas_cost_usd=Decimal("0"),
                execution_time=execution_time,
                error=str(e)
            )
    
    async def _check_flash_loan_opportunity(
        self, 
        token_a: str, 
        token_b: str, 
        dex_a: str, 
        dex_b: str
    ) -> Optional[ArbitrageOpportunity]:
        """Check for flash loan arbitrage opportunity between two DEXes"""
        try:
            # Get prices on both DEXes
            price_dex_a = await self._get_dex_price(token_a, token_b, dex_a)
            price_dex_b = await self._get_dex_price(token_a, token_b, dex_b)
            
            if not price_dex_a or not price_dex_b:
                return None
            
            # Determine which direction is profitable
            if price_dex_b > price_dex_a:
                buy_dex, sell_dex = dex_a, dex_b
                buy_price, sell_price = price_dex_a, price_dex_b
            else:
                buy_dex, sell_dex = dex_b, dex_a
                buy_price, sell_price = price_dex_b, price_dex_a
            
            price_diff = sell_price - buy_price
            profit_percentage = (price_diff / buy_price) * 100
            
            if profit_percentage > Decimal("0.5"):  # Minimum 0.5% price difference
                # Calculate optimal loan amount
                loan_amount = await self._calculate_optimal_loan_amount(
                    token_a, buy_price, sell_price
                )
                
                if loan_amount > Decimal("100"):  # Minimum loan amount
                    # Calculate expected profit
                    profit_usd = await self._calculate_flash_loan_profit(
                        token_a, token_b, loan_amount, buy_price, sell_price
                    )
                    
                    if profit_usd > Decimal("20"):  # Minimum $20 profit
                        return ArbitrageOpportunity(
                            id=f"bsc_flash_{buy_dex}_{sell_dex}_{datetime.now().timestamp()}",
                            type="flash_loan",
                            chain="bsc",
                            token_a=token_a,
                            token_b=token_b,
                            exchange_a=buy_dex,
                            exchange_b=sell_dex,
                            price_a=buy_price,
                            price_b=sell_price,
                            price_difference=price_diff,
                            profit_usd=profit_usd,
                            gas_cost_usd=await self._estimate_flash_loan_gas_cost(),
                            loan_amount=loan_amount,
                            amount_in=loan_amount,
                            amount_out=loan_amount * (sell_price / buy_price),
                            total_liquidity_usd=await self._estimate_dex_liquidity(token_a, token_b),
                            price_impact=await self._estimate_flash_loan_price_impact(loan_amount),
                            timestamp=datetime.now()
                        )
            
            return None
            
        except Exception as e:
            logger.debug(f"Error checking flash loan opportunity: {e}")
            return None
    
    async def _get_dex_price(self, token_a: str, token_b: str, dex: str) -> Optional[Decimal]:
        """Get price from specific DEX"""
        try:
            # Mock price fetching with DEX-specific variations
            base_price = Decimal("600.0")  # Mock base price
            
            dex_variations = {
                "pancakeswap_v2": Decimal("0.0"),
                "pancakeswap_v3": Decimal("0.5"),
                "biswap": Decimal("-1.0"),
                "apeswap": Decimal("1.5")
            }
            
            variation = dex_variations.get(dex, Decimal("0"))
            return base_price + variation
            
        except Exception as e:
            logger.debug(f"Error getting {dex} price: {e}")
            return None
    
    async def _calculate_optimal_loan_amount(
        self, 
        token: str, 
        buy_price: Decimal, 
        sell_price: Decimal
    ) -> Decimal:
        """Calculate optimal flash loan amount"""
        try:
            # Get available liquidity from providers
            max_available = Decimal("0")
            
            for provider_data in self.flash_loan_providers.values():
                provider_max = provider_data["max_amount"].get(token, Decimal("0"))
                max_available = max(max_available, provider_max)
            
            # Calculate amount that maximizes profit considering slippage
            price_diff = sell_price - buy_price
            profit_percentage = price_diff / buy_price
            
            # Conservative amount to minimize slippage
            optimal_amount = min(
                max_available * Decimal("0.1"),  # 10% of max available
                Decimal("1000")  # Cap at reasonable amount
            )
            
            return optimal_amount
            
        except Exception as e:
            logger.error(f"Error calculating optimal loan amount: {e}")
            return Decimal("100")  # Fallback
    
    async def _calculate_flash_loan_profit(
        self, 
        token_a: str, 
        token_b: str, 
        loan_amount: Decimal,
        buy_price: Decimal, 
        sell_price: Decimal
    ) -> Decimal:
        """Calculate expected profit from flash loan arbitrage"""
        try:
            # Calculate revenue from arbitrage
            bought_amount = loan_amount / buy_price
            sold_amount = bought_amount * sell_price
            gross_profit = sold_amount - loan_amount
            
            # Subtract flash loan fee (using Venus as example)
            flash_loan_fee = loan_amount * Decimal("0.0009")
            
            # Subtract DEX fees (0.25% each)
            buy_fee = loan_amount * Decimal("0.0025")
            sell_fee = sold_amount * Decimal("0.0025")
            
            net_profit = gross_profit - flash_loan_fee - buy_fee - sell_fee
            
            # Convert to USD
            token_price_usd = await self._get_token_price_usd(token_a)
            profit_usd = net_profit * token_price_usd
            
            return profit_usd
            
        except Exception as e:
            logger.error(f"Error calculating flash loan profit: {e}")
            return Decimal("0")
    
    async def _get_token_price_usd(self, token: str) -> Decimal:
        """Get token price in USD"""
        # Mock USD prices
        prices = {
            self.config.TOKENS["WBNB"]: Decimal("600.00"),
            self.config.TOKENS["BUSD"]: Decimal("1.00"),
            self.config.TOKENS["USDT"]: Decimal("1.00"),
            self.config.TOKENS["USDC"]: Decimal("1.00"),
            self.config.TOKENS["ETH"]: Decimal("3200.00"),
            self.config.TOKENS["BTCB"]: Decimal("65000.00")
        }
        return prices.get(token, Decimal("1.00"))
    
    async def _estimate_flash_loan_gas_cost(self) -> Decimal:
        """Estimate gas cost for flash loan arbitrage"""
        try:
            # BSC gas cost for flash loan + 2 swaps
            gas_price_gwei = 5
            gas_used = 400000  # Flash loan with swaps
            
            bnb_price_usd = Decimal("600")
            
            gas_cost_bnb = Decimal(str(gas_price_gwei)) * Decimal(str(gas_used)) / Decimal("1e9")
            gas_cost_usd = gas_cost_bnb * bnb_price_usd
            
            return gas_cost_usd
            
        except Exception:
            return Decimal("4.0")  # Fallback
    
    async def _estimate_dex_liquidity(self, token_a: str, token_b: str) -> Decimal:
        """Estimate DEX liquidity"""
        return Decimal("200000")  # $200K mock liquidity
    
    async def _estimate_flash_loan_price_impact(self, loan_amount: Decimal) -> float:
        """Estimate price impact from flash loan arbitrage"""
        # Higher amounts have higher impact
        impact_factor = float(loan_amount) / 10000  # Base factor
        return min(2.0, 0.1 + impact_factor * 0.001)  # Cap at 2%
    
    async def _select_best_provider(self, token: str, amount: Decimal) -> Optional[Dict]:
        """Select best flash loan provider"""
        try:
            best_provider = None
            lowest_fee = Decimal("999")
            
            for provider_name, provider_data in self.flash_loan_providers.items():
                max_amount = provider_data["max_amount"].get(token, Decimal("0"))
                fee = Decimal(str(provider_data["fee"]))
                
                if max_amount >= amount and fee < lowest_fee:
                    lowest_fee = fee
                    best_provider = {
                        "name": provider_name,
                        "data": provider_data
                    }
            
            return best_provider
            
        except Exception as e:
            logger.error(f"Error selecting flash loan provider: {e}")
            return None
    
    async def _execute_flash_loan_arbitrage(
        self, 
        provider: Dict, 
        opportunity: ArbitrageOpportunity
    ) -> Dict[str, Any]:
        """Execute flash loan arbitrage"""
        try:
            logger.info(f"Executing flash loan arbitrage via {provider['name']}")
            
            # Mock execution for now
            # This would deploy and call flash loan contract
            
            # Simulate successful execution
            profit_usd = opportunity.profit_usd * Decimal("0.9")  # 90% of expected
            
            return {
                "success": True,
                "profit_usd": profit_usd,
                "gas_cost_usd": Decimal("4.0"),
                "tx_hash": f"0x{'flashloan' * 8}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "gas_cost_usd": Decimal("0")
            }
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get engine health status"""
        return {
            "status": "healthy" if self.initialized else "uninitialized",
            "initialized": self.initialized,
            "flash_loan_providers": list(self.flash_loan_providers.keys()),
            "dex_combinations": len(self.dex_combinations)
        }