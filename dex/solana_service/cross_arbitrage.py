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

class SolanaCrossArbitrageEngine(BaseArbitrageEngine):
    """Solana Cross-exchange arbitrage engine"""
    
    def __init__(self, engine: SolanaEngine, config: SolanaConfig):
        self.engine = engine
        self.config = config
        self.initialized = False
        
        # Solana DEX configurations
        self.dexes = {
            "jupiter": {
                "program_id": config.JUPITER_V6,
                "aggregator": True,
                "fee": 0.0,  # Jupiter doesn't charge fees, but routes through DEXes that do
                "type": "aggregator"
            },
            "raydium": {
                "program_id": config.RAYDIUM_AMM,
                "fee": 0.0025,  # 0.25%
                "type": "amm"
            },
            "raydium_clmm": {
                "program_id": config.RAYDIUM_CLMM,
                "fee": 0.0025,  # Variable fees
                "type": "clmm"
            },
            "orca": {
                "program_id": config.ORCA_WHIRLPOOL,
                "fee": 0.003,  # Variable fees
                "type": "whirlpool"
            },
            "orca_legacy": {
                "program_id": config.ORCA_LEGACY,
                "fee": 0.003,  # 0.3%
                "type": "legacy_amm"
            },
            "serum": {
                "program_id": config.SERUM_V3,
                "fee": 0.0022,  # 0.22%
                "type": "orderbook"
            }
        }
        
        # Common trading pairs on Solana
        self.trading_pairs = [
            (config.TOKENS["SOL"], config.TOKENS["USDC"]),
            (config.TOKENS["SOL"], config.TOKENS["USDT"]),
            (config.TOKENS["SOL"], config.TOKENS["RAY"]),
            (config.TOKENS["SOL"], config.TOKENS["ORCA"]),
            (config.TOKENS["SOL"], config.TOKENS["SRM"]),
            (config.TOKENS["USDC"], config.TOKENS["USDT"]),
            (config.TOKENS["USDC"], config.TOKENS["RAY"]),
            (config.TOKENS["SOL"], config.TOKENS["BTC"]),
            (config.TOKENS["SOL"], config.TOKENS["ETH"]),
            (config.TOKENS["SOL"], config.TOKENS["BONK"])
        ]
        
    async def initialize(self) -> None:
        """Initialize cross arbitrage engine"""
        try:
            logger.info("Initializing Solana Cross Arbitrage Engine...")
            self.initialized = True
            logger.info("Solana Cross Arbitrage Engine initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Solana cross arbitrage: {e}")
            raise
    
    async def scan_opportunities(self) -> List[ArbitrageOpportunity]:
        """Scan for cross-exchange arbitrage opportunities on Solana"""
        if not self.initialized:
            return []
        
        opportunities = []
        
        try:
            for token_a, token_b in self.trading_pairs:
                # Check prices across different DEXes
                prices = await self._get_prices_across_dexes(token_a, token_b)
                
                if len(prices) >= 2:
                    # Find best buy and sell prices
                    best_buy = min(prices, key=lambda x: x["price"])
                    best_sell = max(prices, key=lambda x: x["price"])
                    
                    if best_buy["dex"] != best_sell["dex"]:
                        price_diff = best_sell["price"] - best_buy["price"]
                        profit_percentage = (price_diff / best_buy["price"]) * 100
                        
                        if profit_percentage > self.config.MIN_PROFIT_THRESHOLD:
                            # Calculate potential profit
                            trade_amount = Decimal("10.0")  # 10 units of token_a
                            
                            profit_usd = await self._calculate_profit(
                                token_a, token_b, trade_amount,
                                best_buy, best_sell
                            )
                            
                            if profit_usd > Decimal("5"):  # Minimum $5 profit
                                opportunity = ArbitrageOpportunity(
                                    id=f"solana_cross_{best_buy['dex']}_{best_sell['dex']}_{datetime.now().timestamp()}",
                                    type="cross_exchange",
                                    chain="solana",
                                    token_a=token_a,
                                    token_b=token_b,
                                    exchange_a=best_buy["dex"],
                                    exchange_b=best_sell["dex"],
                                    price_a=best_buy["price"],
                                    price_b=best_sell["price"],
                                    price_difference=price_diff,
                                    profit_usd=profit_usd,
                                    gas_cost_usd=await self._estimate_transaction_cost(),
                                    amount_in=trade_amount,
                                    amount_out=trade_amount * best_sell["price"],
                                    total_liquidity_usd=await self._estimate_liquidity(token_a, token_b),
                                    price_impact=await self._estimate_price_impact(trade_amount, best_buy, best_sell),
                                    timestamp=datetime.now()
                                )
                                
                                opportunities.append(opportunity)
            
            logger.info(f"Found {len(opportunities)} Solana cross-arbitrage opportunities")
            return opportunities
            
        except Exception as e:
            logger.error(f"Error scanning Solana cross arbitrage opportunities: {e}")
            return []
    
    async def execute_opportunity(self, opportunity: ArbitrageOpportunity) -> ExecutionResult:
        """Execute cross-exchange arbitrage on Solana"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            logger.info(f"Executing Solana cross arbitrage: {opportunity.id}")
            
            # Step 1: Buy on exchange A
            buy_result = await self._execute_buy(
                opportunity.exchange_a,
                opportunity.token_a,
                opportunity.token_b,
                opportunity.amount_in
            )
            
            if not buy_result["success"]:
                raise Exception(f"Buy failed: {buy_result['error']}")
            
            # Step 2: Sell on exchange B
            sell_result = await self._execute_sell(
                opportunity.exchange_b,
                opportunity.token_b,
                opportunity.token_a,
                buy_result["amount_out"]
            )
            
            if not sell_result["success"]:
                raise Exception(f"Sell failed: {sell_result['error']}")
            
            execution_time = asyncio.get_event_loop().time() - start_time
            
            # Calculate actual profit
            actual_profit = sell_result["amount_out"] - opportunity.amount_in
            
            return ExecutionResult(
                opportunity_id=opportunity.id,
                success=True,
                profit_usd=actual_profit * opportunity.price_a,  # Convert to USD
                gas_cost_usd=buy_result["transaction_cost"] + sell_result["transaction_cost"],
                execution_time=execution_time,
                transaction_hashes=[buy_result["tx_signature"], sell_result["tx_signature"]]
            )
            
        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"Solana cross arbitrage execution failed: {e}")
            
            return ExecutionResult(
                opportunity_id=opportunity.id,
                success=False,
                profit_usd=Decimal("0"),
                gas_cost_usd=Decimal("0"),
                execution_time=execution_time,
                error=str(e)
            )
    
    async def _get_prices_across_dexes(self, token_a: str, token_b: str) -> List[Dict[str, Any]]:
        """Get prices for token pair across all DEXes"""
        prices = []
        
        for dex_name, dex_config in self.dexes.items():
            try:
                if dex_config["type"] == "aggregator":
                    price = await self._get_jupiter_price(token_a, token_b)
                elif dex_config["type"] == "amm":
                    price = await self._get_amm_price(token_a, token_b, dex_config)
                elif dex_config["type"] == "clmm":
                    price = await self._get_clmm_price(token_a, token_b, dex_config)
                elif dex_config["type"] == "whirlpool":
                    price = await self._get_whirlpool_price(token_a, token_b, dex_config)
                elif dex_config["type"] == "orderbook":
                    price = await self._get_orderbook_price(token_a, token_b, dex_config)
                else:
                    price = await self._get_generic_price(token_a, token_b, dex_config)
                
                if price and price > 0:
                    prices.append({
                        "dex": dex_name,
                        "price": price,
                        "config": dex_config
                    })
                    
            except Exception as e:
                logger.debug(f"Error getting price from {dex_name}: {e}")
                continue
        
        return prices
    
    async def _get_jupiter_price(self, token_a: str, token_b: str) -> Optional[Decimal]:
        """Get price from Jupiter aggregator"""
        try:
            # Use real Jupiter API integration
            price = await self.engine.get_token_price_jupiter(token_a, token_b)
            return price
        except Exception as e:
            logger.debug(f"Error getting Jupiter price: {e}")
            return None
    
    async def _get_amm_price(self, token_a: str, token_b: str, dex_config: Dict) -> Optional[Decimal]:
        """Get price from AMM DEX (Raydium)"""
        try:
            if dex_config["program_id"] == self.config.RAYDIUM_AMM:
                return await self._get_raydium_price(token_a, token_b)
            else:
                # Fallback to Jupiter for other AMMs
                return await self._get_jupiter_price(token_a, token_b)
        except Exception as e:
            logger.debug(f"Error getting AMM price: {e}")
            return None
    
    async def _get_clmm_price(self, token_a: str, token_b: str, dex_config: Dict) -> Optional[Decimal]:
        """Get price from Concentrated Liquidity Market Maker"""
        try:
            # Use Jupiter for CLMM pools as well
            return await self.engine.get_token_price_jupiter(token_a, token_b)
        except Exception as e:
            logger.debug(f"Error getting CLMM price: {e}")
            return None
    
    async def _get_whirlpool_price(self, token_a: str, token_b: str, dex_config: Dict) -> Optional[Decimal]:
        """Get price from Whirlpool DEX (Orca)"""
        try:
            return await self._get_orca_price(token_a, token_b)
        except Exception as e:
            logger.debug(f"Error getting Whirlpool price: {e}")
            return None
    
    async def _get_orderbook_price(self, token_a: str, token_b: str, dex_config: Dict) -> Optional[Decimal]:
        """Get price from orderbook DEX (Serum)"""
        try:
            return await self._get_serum_price(token_a, token_b)
        except Exception as e:
            logger.debug(f"Error getting orderbook price: {e}")
            return None
    
    async def _get_generic_price(self, token_a: str, token_b: str, dex_config: Dict) -> Optional[Decimal]:
        """Get price from generic DEX"""
        try:
            # Use Jupiter for generic DEX pricing
            return await self.engine.get_token_price_jupiter(token_a, token_b)
        except Exception as e:
            logger.debug(f"Error getting generic price: {e}")
            return None
    
    async def _get_raydium_price(self, token_a: str, token_b: str) -> Optional[Decimal]:
        """Get price from Raydium AMM pools"""
        try:
            # Use Jupiter as it aggregates Raydium pools
            # In a more advanced implementation, you could query Raydium pools directly
            return await self.engine.get_token_price_jupiter(token_a, token_b)
        except Exception as e:
            logger.debug(f"Error getting Raydium price: {e}")
            return None
    
    async def _get_orca_price(self, token_a: str, token_b: str) -> Optional[Decimal]:
        """Get price from Orca Whirlpools"""
        try:
            # Use Jupiter as it aggregates Orca pools
            # In a more advanced implementation, you could query Orca pools directly
            return await self.engine.get_token_price_jupiter(token_a, token_b)
        except Exception as e:
            logger.debug(f"Error getting Orca price: {e}")
            return None
    
    async def _get_serum_price(self, token_a: str, token_b: str) -> Optional[Decimal]:
        """Get price from Serum orderbook"""
        try:
            # Use Jupiter as it can route through Serum
            # In a more advanced implementation, you could query Serum orderbooks directly
            return await self.engine.get_token_price_jupiter(token_a, token_b)
        except Exception as e:
            logger.debug(f"Error getting Serum price: {e}")
            return None
    
    def _is_stablecoin_pair(self, token_a: str, token_b: str) -> bool:
        """Check if pair consists of stablecoins"""
        stablecoins = [
            self.config.TOKENS["USDC"],
            self.config.TOKENS["USDT"]
        ]
        return token_a in stablecoins and token_b in stablecoins
    
    async def _calculate_profit(
        self, 
        token_a: str, 
        token_b: str, 
        amount: Decimal,
        buy_data: Dict,
        sell_data: Dict
    ) -> Decimal:
        """Calculate expected profit in USD"""
        try:
            buy_cost = amount * buy_data["price"]
            sell_revenue = amount * sell_data["price"]
            
            # Subtract DEX fees
            buy_fee = buy_cost * Decimal(str(buy_data["config"].get("fee", 0.003)))
            sell_fee = sell_revenue * Decimal(str(sell_data["config"].get("fee", 0.003)))
            
            gross_profit = sell_revenue - buy_cost
            net_profit = gross_profit - buy_fee - sell_fee
            
            # Convert to USD
            token_price_usd = await self._get_token_price_usd(token_a)
            return net_profit * token_price_usd
            
        except Exception as e:
            logger.error(f"Error calculating Solana profit: {e}")
            return Decimal("0")
    
    async def _get_token_price_usd(self, token: str) -> Decimal:
        """Get token price in USD using real price feeds"""
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
        """Estimate transaction cost in USD"""
        try:
            # Solana transaction costs are very low
            base_fee_lamports = 5000  # Base transaction fee
            compute_fee_lamports = self.config.PRIORITY_FEE_LAMPORTS
            
            total_fee_lamports = base_fee_lamports + compute_fee_lamports
            total_fee_sol = Decimal(total_fee_lamports) / Decimal(self.config.LAMPORTS_PER_SOL)
            
            sol_price_usd = Decimal("180.00")
            transaction_cost_usd = total_fee_sol * sol_price_usd
            
            return transaction_cost_usd
            
        except Exception:
            return Decimal("0.01")  # Very low fallback
    
    async def _estimate_liquidity(self, token_a: str, token_b: str) -> Decimal:
        """Estimate available liquidity using Jupiter quote"""
        try:
            # Get a large quote to estimate available liquidity
            token_a_decimals = await self.engine._get_token_decimals(token_a)
            large_amount = 10 ** (token_a_decimals + 3)  # 1000 units
            
            quote = await self.engine._get_jupiter_quote(token_a, token_b, large_amount)
            
            if quote and "priceImpactPct" in quote:
                price_impact = float(quote["priceImpactPct"])
                
                # Estimate liquidity based on price impact
                # Lower price impact = higher liquidity
                if price_impact < 0.1:  # < 0.1% impact
                    return Decimal("10000000")  # $10M+
                elif price_impact < 0.5:  # < 0.5% impact
                    return Decimal("5000000")   # $5M
                elif price_impact < 1.0:  # < 1% impact
                    return Decimal("2000000")   # $2M
                else:
                    return Decimal("500000")    # $500K
            
            return Decimal("1000000")  # Default $1M
            
        except Exception as e:
            logger.debug(f"Error estimating liquidity: {e}")
            return Decimal("1000000")  # Default fallback
    
    async def _estimate_price_impact(
        self, 
        amount: Decimal, 
        buy_data: Dict, 
        sell_data: Dict
    ) -> float:
        """Estimate price impact using real quotes"""
        try:
            total_impact = 0.0
            
            # Get price impact for buy side
            if "token_a" in buy_data and "token_b" in buy_data:
                token_a_decimals = await self.engine._get_token_decimals(buy_data["token_a"])
                amount_raw = int(amount * Decimal(10 ** token_a_decimals))
                
                quote = await self.engine._get_jupiter_quote(
                    buy_data["token_a"], buy_data["token_b"], amount_raw
                )
                
                if quote and "priceImpactPct" in quote:
                    total_impact += float(quote["priceImpactPct"])
            
            # Get price impact for sell side
            if "token_a" in sell_data and "token_b" in sell_data:
                token_a_decimals = await self.engine._get_token_decimals(sell_data["token_a"])
                amount_raw = int(amount * Decimal(10 ** token_a_decimals))
                
                quote = await self.engine._get_jupiter_quote(
                    sell_data["token_a"], sell_data["token_b"], amount_raw
                )
                
                if quote and "priceImpactPct" in quote:
                    total_impact += float(quote["priceImpactPct"])
            
            return total_impact / 100.0  # Convert percentage to decimal
            
        except Exception as e:
            logger.debug(f"Error estimating price impact: {e}")
            return 0.05  # 0.05% fallback
    
    async def _execute_buy(
        self, 
        dex: str, 
        token_in: str, 
        token_out: str, 
        amount_in: Decimal
    ) -> Dict[str, Any]:
        """Execute buy order on specified DEX"""
        try:
            logger.info(f"Executing buy on {dex}: {amount_in} {token_in} -> {token_out}")
            
            # Convert to lamports/smallest unit
            token_in_decimals = await self.engine._get_token_decimals(token_in)
            amount_in_raw = int(amount_in * Decimal(10 ** token_in_decimals))
            
            # Execute swap using Jupiter (which routes through the best DEX)
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
            logger.error(f"Error executing buy: {e}")
            return {
                "success": False,
                "error": str(e),
                "transaction_cost": Decimal("0")
            }
    
    async def _execute_sell(
        self, 
        dex: str, 
        token_in: str, 
        token_out: str, 
        amount_in: Decimal
    ) -> Dict[str, Any]:
        """Execute sell order on specified DEX"""
        try:
            logger.info(f"Executing sell on {dex}: {amount_in} {token_in} -> {token_out}")
            
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
            logger.error(f"Error executing sell: {e}")
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
            "supported_dexes": list(self.dexes.keys()),
            "trading_pairs": len(self.trading_pairs)
        }