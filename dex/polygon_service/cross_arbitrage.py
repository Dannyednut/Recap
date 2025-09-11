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

class PolygonCrossArbitrageEngine(BaseArbitrageEngine):
    """Polygon Cross-exchange arbitrage engine"""
    
    def __init__(self, engine: PolygonEngine, config: PolygonConfig):
        self.engine = engine
        self.config = config
        self.initialized = False
        
        # Polygon DEX configurations
        self.dexes = {
            "uniswap_v3": {
                "router": config.UNISWAP_V3_ROUTER,
                "factory": config.UNISWAP_V3_FACTORY,
                "quoter": config.UNISWAP_V3_QUOTER_V2,
                "fee_tiers": [100, 500, 3000, 10000],  # 0.01%, 0.05%, 0.3%, 1%
                "type": "v3"
            },
            "quickswap": {
                "router": config.QUICKSWAP_V2_ROUTER,
                "factory": config.QUICKSWAP_V2_FACTORY,
                "fee": 0.003,  # 0.3%
                "type": "v2"
            },
            "sushiswap": {
                "router": config.SUSHISWAP_ROUTER,
                "factory": config.SUSHISWAP_FACTORY,
                "fee": 0.003,  # 0.3%
                "type": "v2"
            },
            "curve": {
                "registry": config.CURVE_REGISTRY,
                "fee": 0.0004,  # Variable, 0.04% average
                "type": "curve"
            }
        }
        
        # Common trading pairs on Polygon
        self.trading_pairs = [
            (config.TOKENS["WMATIC"], config.TOKENS["USDC"]),
            (config.TOKENS["WMATIC"], config.TOKENS["USDT"]),
            (config.TOKENS["WMATIC"], config.TOKENS["DAI"]),
            (config.TOKENS["WMATIC"], config.TOKENS["WETH"]),
            (config.TOKENS["WMATIC"], config.TOKENS["WBTC"]),
            (config.TOKENS["USDC"], config.TOKENS["USDT"]),
            (config.TOKENS["USDC"], config.TOKENS["DAI"]),
            (config.TOKENS["WETH"], config.TOKENS["USDC"]),
            (config.TOKENS["WBTC"], config.TOKENS["USDC"])
        ]
        
    async def initialize(self) -> None:
        """Initialize cross arbitrage engine"""
        try:
            logger.info("Initializing Polygon Cross Arbitrage Engine...")
            self.initialized = True
            logger.info("Polygon Cross Arbitrage Engine initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Polygon cross arbitrage: {e}")
            raise
    
    async def scan_opportunities(self) -> List[ArbitrageOpportunity]:
        """Scan for cross-exchange arbitrage opportunities on Polygon"""
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
                            trade_amount = Decimal("100.0")  # 100 units of token_a
                            
                            profit_usd = await self._calculate_profit(
                                token_a, token_b, trade_amount,
                                best_buy, best_sell
                            )
                            
                            if profit_usd > Decimal("15"):  # Minimum $15 profit
                                opportunity = ArbitrageOpportunity(
                                    id=f"polygon_cross_{best_buy['dex']}_{best_sell['dex']}_{datetime.now().timestamp()}",
                                    type="cross_exchange",
                                    chain="polygon",
                                    token_a=token_a,
                                    token_b=token_b,
                                    exchange_a=best_buy["dex"],
                                    exchange_b=best_sell["dex"],
                                    price_a=best_buy["price"],
                                    price_b=best_sell["price"],
                                    price_difference=price_diff,
                                    profit_usd=profit_usd,
                                    gas_cost_usd=await self._estimate_gas_cost(),
                                    amount_in=trade_amount,
                                    amount_out=trade_amount * best_sell["price"],
                                    total_liquidity_usd=await self._estimate_liquidity(token_a, token_b),
                                    price_impact=await self._estimate_price_impact(trade_amount, best_buy, best_sell),
                                    timestamp=datetime.now()
                                )
                                
                                opportunities.append(opportunity)
            
            logger.info(f"Found {len(opportunities)} Polygon cross-arbitrage opportunities")
            return opportunities
            
        except Exception as e:
            logger.error(f"Error scanning Polygon cross arbitrage opportunities: {e}")
            return []
    
    async def execute_opportunity(self, opportunity: ArbitrageOpportunity) -> ExecutionResult:
        """Execute cross-exchange arbitrage on Polygon"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            logger.info(f"Executing Polygon cross arbitrage: {opportunity.id}")
            
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
                gas_cost_usd=buy_result["gas_cost"] + sell_result["gas_cost"],
                execution_time=execution_time,
                transaction_hashes=[buy_result["tx_hash"], sell_result["tx_hash"]]
            )
            
        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"Polygon cross arbitrage execution failed: {e}")
            
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
                if dex_config["type"] == "v2":
                    price = await self._get_v2_price(token_a, token_b, dex_config)
                elif dex_config["type"] == "v3":
                    price = await self._get_v3_price(token_a, token_b, dex_config)
                elif dex_config["type"] == "curve":
                    price = await self._get_curve_price(token_a, token_b, dex_config)
                
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
    
    async def _get_v2_price(self, token_a: str, token_b: str, dex_config: Dict) -> Optional[Decimal]:
        """Get price from V2 DEX"""
        try:
            # Mock price with DEX-specific variations
            base_price = await self._get_base_price(token_a, token_b)
            variation = Decimal("0.005") * (hash(dex_config["router"]) % 20 - 10)  # -5% to +5%
            return base_price * (1 + variation)
            
        except Exception as e:
            logger.debug(f"Error getting V2 price: {e}")
            return None
    
    async def _get_v3_price(self, token_a: str, token_b: str, dex_config: Dict) -> Optional[Decimal]:
        """Get price from V3 DEX using quoter"""
        try:
            base_price = await self._get_base_price(token_a, token_b)
            variation = Decimal("0.003") * (hash(dex_config["quoter"]) % 20 - 10)  # -3% to +3%
            return base_price * (1 + variation)
            
        except Exception as e:
            logger.debug(f"Error getting V3 price: {e}")
            return None
    
    async def _get_curve_price(self, token_a: str, token_b: str, dex_config: Dict) -> Optional[Decimal]:
        """Get price from Curve (stablecoin pairs mainly)"""
        try:
            # Curve is mainly for stablecoins, should have tight spreads
            if self._is_stablecoin_pair(token_a, token_b):
                base_price = Decimal("1.0")  # Near 1:1 for stablecoins
                variation = Decimal("0.001") * (hash(dex_config["registry"]) % 10 - 5)  # -0.5% to +0.5%
                return base_price * (1 + variation)
            return None
            
        except Exception as e:
            logger.debug(f"Error getting Curve price: {e}")
            return None
    
    def _is_stablecoin_pair(self, token_a: str, token_b: str) -> bool:
        """Check if pair consists of stablecoins"""
        stablecoins = [
            self.config.TOKENS["USDC"],
            self.config.TOKENS["USDT"],
            self.config.TOKENS["DAI"]
        ]
        return token_a in stablecoins and token_b in stablecoins
    
    async def _get_base_price(self, token_a: str, token_b: str) -> Decimal:
        """Get base price for token pair"""
        # Mock base prices for common pairs
        if token_a == self.config.TOKENS["WMATIC"]:
            if token_b == self.config.TOKENS["USDC"]:
                return Decimal("0.85")  # MATIC/USDC
            elif token_b == self.config.TOKENS["WETH"]:
                return Decimal("0.00026")  # MATIC/WETH
        elif self._is_stablecoin_pair(token_a, token_b):
            return Decimal("1.0")  # Stablecoin pairs
        
        return Decimal("1.0")  # Default
    
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
            
            # Subtract fees
            buy_fee = buy_cost * Decimal(str(buy_data["config"].get("fee", 0.003)))
            sell_fee = sell_revenue * Decimal(str(sell_data["config"].get("fee", 0.003)))
            
            gross_profit = sell_revenue - buy_cost
            net_profit = gross_profit - buy_fee - sell_fee
            
            # Convert to USD
            token_price_usd = await self._get_token_price_usd(token_a)
            return net_profit * token_price_usd
            
        except Exception as e:
            logger.error(f"Error calculating Polygon profit: {e}")
            return Decimal("0")
    
    async def _get_token_price_usd(self, token: str) -> Decimal:
        """Get token price in USD"""
        # Mock USD prices
        prices = {
            self.config.TOKENS["WMATIC"]: Decimal("0.85"),
            self.config.TOKENS["USDC"]: Decimal("1.00"),
            self.config.TOKENS["USDT"]: Decimal("1.00"),
            self.config.TOKENS["DAI"]: Decimal("1.00"),
            self.config.TOKENS["WETH"]: Decimal("3200.00"),
            self.config.TOKENS["WBTC"]: Decimal("65000.00")
        }
        return prices.get(token, Decimal("1.00"))
    
    async def _estimate_gas_cost(self) -> Decimal:
        """Estimate gas cost for cross arbitrage in USD"""
        try:
            # Polygon gas is very low
            gas_price_gwei = 30  # 30 Gwei typical
            gas_used = 200000  # Two swaps
            
            matic_price_usd = Decimal("0.85")
            
            gas_cost_matic = Decimal(str(gas_price_gwei)) * Decimal(str(gas_used)) / Decimal("1e9")
            gas_cost_usd = gas_cost_matic * matic_price_usd
            
            return gas_cost_usd
            
        except Exception:
            return Decimal("0.50")  # Fallback - very low
    
    async def _estimate_liquidity(self, token_a: str, token_b: str) -> Decimal:
        """Estimate available liquidity"""
        return Decimal("500000")  # $500K mock liquidity
    
    async def _estimate_price_impact(
        self, 
        amount: Decimal, 
        buy_data: Dict, 
        sell_data: Dict
    ) -> float:
        """Estimate price impact"""
        return 0.08  # 0.08% estimated impact
    
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
            
            # Mock execution
            return {
                "success": True,
                "amount_out": amount_in * Decimal("0.997"),  # After fees
                "tx_hash": f"0x{'polygon_buy' * 7}",
                "gas_cost": Decimal("0.25")
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "gas_cost": Decimal("0")
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
            
            # Mock execution
            return {
                "success": True,
                "amount_out": amount_in * Decimal("1.005"),  # Favorable rate
                "tx_hash": f"0x{'polygon_sell' * 7}",
                "gas_cost": Decimal("0.25")
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "gas_cost": Decimal("0")
            }
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get engine health status"""
        return {
            "status": "healthy" if self.initialized else "uninitialized",
            "initialized": self.initialized,
            "supported_dexes": list(self.dexes.keys()),
            "trading_pairs": len(self.trading_pairs)
        }