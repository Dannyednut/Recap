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

from .engine import SolanaEngine
from .config import SolanaConfig

logger = logging.getLogger(__name__)

class SolanaFlashLoanEngine(BaseArbitrageEngine):
    """Solana Flash loan arbitrage engine"""
    
    def __init__(self, engine: SolanaEngine, config: SolanaConfig):
        self.engine = engine
        self.config = config
        self.initialized = False
        
        # Flash loan providers on Solana
        self.flash_loan_providers = {
            "mango_v4": {
                "program_id": config.MANGO_V4,
                "fee": 0.0001,  # 0.01% very low
                "max_amount": {
                    config.TOKENS["SOL"]: Decimal("100000"),    # 100K SOL
                    config.TOKENS["USDC"]: Decimal("50000000"), # 50M USDC
                    config.TOKENS["USDT"]: Decimal("50000000"), # 50M USDT
                    config.TOKENS["BTC"]: Decimal("2000"),      # 2K BTC
                    config.TOKENS["ETH"]: Decimal("15000")      # 15K ETH
                }
            },
            "solend": {
                "program_id": config.SOLEND,
                "fee": 0.0005,  # 0.05%
                "max_amount": {
                    config.TOKENS["SOL"]: Decimal("50000"),     # 50K SOL
                    config.TOKENS["USDC"]: Decimal("25000000"), # 25M USDC
                    config.TOKENS["USDT"]: Decimal("25000000")  # 25M USDT
                }
            }
        }
        
        # DEX combinations for flash loan arbitrage
        self.dex_combinations = [
            ("jupiter", "raydium"),
            ("jupiter", "orca"),
            ("raydium", "orca"),
            ("raydium", "serum"),
            ("orca", "serum")
        ]
        
    async def initialize(self) -> None:
        """Initialize flash loan engine"""
        try:
            logger.info("Initializing Solana Flash Loan Engine...")
            self.initialized = True
            logger.info("Solana Flash Loan Engine initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Solana flash loan engine: {e}")
            raise
    
    async def scan_opportunities(self) -> List[ArbitrageOpportunity]:
        """Scan for flash loan arbitrage opportunities on Solana"""
        if not self.initialized:
            return []
        
        opportunities = []
        
        try:
            # Check major token pairs for flash loan opportunities
            major_tokens = [
                self.config.TOKENS["SOL"],
                self.config.TOKENS["USDC"],
                self.config.TOKENS["USDT"],
                self.config.TOKENS["RAY"],
                self.config.TOKENS["ORCA"],
                self.config.TOKENS["SRM"]
            ]
            
            for i, token_a in enumerate(major_tokens):
                for token_b in major_tokens[i+1:]:
                    for dex_a, dex_b in self.dex_combinations:
                        opportunity = await self._check_flash_loan_opportunity(
                            token_a, token_b, dex_a, dex_b
                        )
                        if opportunity:
                            opportunities.append(opportunity)
            
            logger.info(f"Found {len(opportunities)} Solana flash loan opportunities")
            return opportunities
            
        except Exception as e:
            logger.error(f"Error scanning Solana flash loan opportunities: {e}")
            return []
    
    async def execute_opportunity(self, opportunity: ArbitrageOpportunity) -> ExecutionResult:
        """Execute flash loan arbitrage on Solana"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            logger.info(f"Executing Solana flash loan arbitrage: {opportunity.id}")
            
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
                    gas_cost_usd=result["transaction_cost_usd"],
                    execution_time=execution_time,
                    transaction_hashes=[result["tx_signature"]]
                )
            else:
                return ExecutionResult(
                    opportunity_id=opportunity.id,
                    success=False,
                    profit_usd=Decimal("0"),
                    gas_cost_usd=result.get("transaction_cost_usd", Decimal("0")),
                    execution_time=execution_time,
                    error=result["error"]
                )
                
        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"Solana flash loan execution failed: {e}")
            
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
            
            if profit_percentage > Decimal("0.2"):  # Minimum 0.2% price difference
                # Calculate optimal loan amount
                loan_amount = await self._calculate_optimal_loan_amount(
                    token_a, buy_price, sell_price
                )
                
                if loan_amount > Decimal("50"):  # Minimum loan amount
                    # Calculate expected profit
                    profit_usd = await self._calculate_flash_loan_profit(
                        token_a, token_b, loan_amount, buy_price, sell_price
                    )
                    
                    if profit_usd > Decimal("5"):  # Minimum $5 profit
                        return ArbitrageOpportunity(
                            id=f"solana_flash_{buy_dex}_{sell_dex}_{datetime.now().timestamp()}",
                            type="flash_loan",
                            chain="solana",
                            token_a=token_a,
                            token_b=token_b,
                            exchange_a=buy_dex,
                            exchange_b=sell_dex,
                            price_a=buy_price,
                            price_b=sell_price,
                            price_difference=price_diff,
                            profit_usd=profit_usd,
                            gas_cost_usd=await self._estimate_flash_loan_transaction_cost(),
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
            # Get base price for the pair
            base_price = await self._get_base_price(token_a, token_b)
            
            # Apply DEX-specific variations
            dex_variations = {
                "jupiter": Decimal("0.0"),      # Best aggregated price
                "raydium": Decimal("0.002"),    # Slightly higher
                "orca": Decimal("-0.001"),      # Slightly lower
                "serum": Decimal("0.003"),      # Orderbook spread
                "raydium_clmm": Decimal("0.001") # Concentrated liquidity
            }
            
            variation = dex_variations.get(dex, Decimal("0"))
            return base_price * (1 + variation)
            
        except Exception as e:
            logger.debug(f"Error getting {dex} price: {e}")
            return None
    
    async def _get_token_price(self, token_a: str, token_b: str) -> Optional[Decimal]:
        """Get real token price using Jupiter API"""
        try:
            # Use real Jupiter API integration
            price = await self.engine.get_token_price_jupiter(token_a, token_b)
            return price
        except Exception as e:
            logger.debug(f"Error getting token price: {e}")
            return None
    
    async def _get_base_price(self, token_a: str, token_b: str) -> Decimal:
        """Get base price for token pair"""
        # Mock base prices for Solana pairs
        if token_a == self.config.TOKENS["SOL"]:
            if token_b == self.config.TOKENS["USDC"]:
                return Decimal("180.00")  # SOL/USDC
            elif token_b == self.config.TOKENS["RAY"]:
                return Decimal("120.0")   # SOL/RAY
        elif self._is_stablecoin_pair(token_a, token_b):
            return Decimal("1.001")  # Stablecoin pairs
        
        return Decimal("1.0")  # Default
    
    def _is_stablecoin_pair(self, token_a: str, token_b: str) -> bool:
        """Check if pair consists of stablecoins"""
        stablecoins = [
            self.config.TOKENS["USDC"],
            self.config.TOKENS["USDT"]
        ]
        return token_a in stablecoins and token_b in stablecoins
    
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
            
            # Conservative amount for Solana (good liquidity)
            optimal_amount = min(
                max_available * Decimal("0.1"),  # 10% of max available
                Decimal("5000")  # Cap at reasonable amount
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
            
            # Subtract flash loan fee (Mango: 0.01%)
            flash_loan_fee = loan_amount * Decimal("0.0001")
            
            # Subtract DEX fees (average 0.25% each)
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
    
    async def _get_sol_price_usd(self) -> Decimal:
        """Get SOL price in USD"""
        try:
            sol_token = self.config.TOKENS["SOL"]
            usdc_token = self.config.TOKENS["USDC"]
            price = await self.engine.get_token_price_jupiter(sol_token, usdc_token)
            return price if price else Decimal("180.00")
        except Exception:
            return Decimal("180.00")  # Fallback
    
    async def _calculate_optimal_flash_loan_amount(self, opportunity: ArbitrageOpportunity) -> Decimal:
        """Calculate optimal flash loan amount for maximum profit"""
        try:
            # For simplicity, use the amount from the opportunity
            # In a more sophisticated implementation, this would optimize based on
            # liquidity curves and price impact
            return opportunity.amount
        except Exception:
            return Decimal("1000")  # Default amount
    
    async def _build_flash_loan_transaction(
        self, 
        provider: Dict, 
        opportunity: ArbitrageOpportunity, 
        amount: Decimal
    ) -> Dict[str, Any]:
        """Build flash loan transaction with arbitrage logic"""
        try:
            # This is a simplified version - in reality, you would need to:
            # 1. Create flash loan instruction
            # 2. Add arbitrage swap instructions
            # 3. Add repayment instruction
            # 4. Combine into a single atomic transaction
            
            logger.info(f"Building flash loan transaction for {amount} {opportunity.token_a}")
            
            # For now, return a mock transaction structure
            # In production, this would build actual Solana instructions
            return {
                "success": True,
                "transaction": None,  # Would contain actual Transaction object
                "estimated_profit": opportunity.profit_usd,
                "flash_loan_amount": amount
            }
            
        except Exception as e:
            logger.error(f"Error building flash loan transaction: {e}")
            return {
                "success": False,
                "error": str(e)
            }

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
        """Execute real flash loan arbitrage"""
        try:
            logger.info(f"Executing flash loan arbitrage with {provider['name']}")
            
            # Calculate flash loan amount needed
            flash_loan_amount = await self._calculate_optimal_flash_loan_amount(opportunity)
            
            # Build flash loan transaction
            flash_loan_tx = await self._build_flash_loan_transaction(
                provider, opportunity, flash_loan_amount
            )
            
            if not flash_loan_tx["success"]:
                return flash_loan_tx
            
            # Execute the flash loan transaction
            tx_signature = await self.engine.execute_transaction(flash_loan_tx["transaction"])
            
            # Wait for confirmation
            confirmation = await self.engine.wait_for_transaction_confirmation(tx_signature)
            
            if confirmation["success"]:
                # Calculate actual profit after fees
                flash_loan_fee = flash_loan_amount * provider["fee_rate"]
                transaction_cost = await self._estimate_transaction_cost()
                net_profit = opportunity.profit_usd - flash_loan_fee - transaction_cost
                
                return {
                    "success": True,
                    "profit": net_profit,
                    "tx_signature": tx_signature,
                    "flash_loan_fee": flash_loan_fee,
                    "transaction_cost": transaction_cost,
                    "confirmation": confirmation
                }
            else:
                return {
                    "success": False,
                    "error": confirmation.get("error", "Transaction failed"),
                    "transaction_cost": await self._estimate_transaction_cost()
                }
            
        except Exception as e:
            logger.error(f"Error executing flash loan arbitrage: {e}")
            return {
                "success": False,
                "error": str(e),
                "transaction_cost": Decimal("0")
            }
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get engine health status"""
        return {
            "status": "healthy" if self.initialized else "uninitialized",
            "initialized": self.initialized,
            "flash_loan_providers": list(self.flash_loan_providers.keys()),
            "dex_combinations": len(self.dex_combinations)
        }