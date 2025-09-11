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

from .engine import BSCEngine
from .config import BSCConfig

logger = logging.getLogger(__name__)

class BSCCrossArbitrageEngine(BaseArbitrageEngine):
    """BSC Cross-exchange arbitrage engine"""
    
    def __init__(self, engine: BSCEngine, config: BSCConfig):
        self.engine = engine
        self.config = config
        self.initialized = False
        
        # BSC DEX configurations
        self.dexes = {
            "pancakeswap_v2": {
                "router": config.PANCAKESWAP_V2_ROUTER,
                "factory": config.PANCAKESWAP_V2_FACTORY,
                "fee": 0.0025,  # 0.25%
                "type": "v2"
            },
            "pancakeswap_v3": {
                "router": config.PANCAKESWAP_V3_ROUTER,
                "factory": config.PANCAKESWAP_V3_FACTORY,
                "quoter": config.PANCAKESWAP_V3_QUOTER_V2,
                "fee_tiers": [100, 500, 2500, 10000],  # 0.01%, 0.05%, 0.25%, 1%
                "type": "v3"
            },
            "biswap": {
                "router": config.BISWAP_ROUTER,
                "factory": config.BISWAP_FACTORY,
                "fee": 0.001,  # 0.1%
                "type": "v2"
            },
            "apeswap": {
                "router": config.APESWAP_ROUTER,
                "factory": config.APESWAP_FACTORY,
                "fee": 0.002,  # 0.2%
                "type": "v2"
            }
        }
        
        # Common trading pairs on BSC
        self.trading_pairs = [
            (config.TOKENS["WBNB"], config.TOKENS["BUSD"]),
            (config.TOKENS["WBNB"], config.TOKENS["USDT"]),
            (config.TOKENS["WBNB"], config.TOKENS["USDC"]),
            (config.TOKENS["BUSD"], config.TOKENS["USDT"]),
            (config.TOKENS["BUSD"], config.TOKENS["USDC"]),
            (config.TOKENS["WBNB"], config.TOKENS["ETH"]),
            (config.TOKENS["WBNB"], config.TOKENS["BTCB"]),
            (config.TOKENS["WBNB"], config.TOKENS["CAKE"])
        ]
        
    async def initialize(self) -> None:
        """Initialize cross arbitrage engine"""
        try:
            logger.info("Initializing BSC Cross Arbitrage Engine...")
            self.initialized = True
            logger.info("BSC Cross Arbitrage Engine initialized")
        except Exception as e:
            logger.error(f"Failed to initialize BSC cross arbitrage: {e}")
            raise
    
    async def scan_opportunities(self) -> List[ArbitrageOpportunity]:
        """Scan for cross-exchange arbitrage opportunities on BSC"""
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
                            trade_amount = Decimal("1.0")  # 1 unit of token_a
                            
                            profit_usd = await self._calculate_profit(
                                token_a, token_b, trade_amount,
                                best_buy, best_sell
                            )
                            
                            if profit_usd > Decimal("10"):  # Minimum $10 profit
                                opportunity = ArbitrageOpportunity(
                                    id=f"bsc_cross_{best_buy['dex']}_{best_sell['dex']}_{datetime.now().timestamp()}",
                                    type="cross_exchange",
                                    chain="bsc",
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
            
            logger.info(f"Found {len(opportunities)} BSC cross-arbitrage opportunities")
            return opportunities
            
        except Exception as e:
            logger.error(f"Error scanning BSC cross arbitrage opportunities: {e}")
            return []
    
    async def execute_opportunity(self, opportunity: ArbitrageOpportunity) -> ExecutionResult:
        """Execute cross-exchange arbitrage on BSC"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            logger.info(f"Executing BSC cross arbitrage: {opportunity.id}")
            
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
            logger.error(f"BSC cross arbitrage execution failed: {e}")
            
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
                else:  # v3
                    price = await self._get_v3_price(token_a, token_b, dex_config)
                
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
        """Get price from V2 DEX (simplified)"""
        try:
            # This would call the pair contract to get reserves
            # For now, return a mock price with some variation
            base_price = Decimal("400.50")  # Mock WBNB/BUSD price
            variation = Decimal("0.01") * (hash(dex_config["router"]) % 100)
            return base_price + variation
            
        except Exception as e:
            logger.debug(f"Error getting V2 price: {e}")
            return None
    
    async def _get_v3_price(self, token_a: str, token_b: str, dex_config: Dict) -> Optional[Decimal]:
        """Get price from V3 DEX using quoter"""
        try:
            # This would call the quoter contract
            # For now, return a mock price with different variation
            base_price = Decimal("400.75")  # Mock WBNB/BUSD price
            variation = Decimal("0.02") * (hash(dex_config["quoter"]) % 50)
            return base_price + variation
            
        except Exception as e:
            logger.debug(f"Error getting V3 price: {e}")
            return None
    
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
            buy_fee = buy_cost * Decimal(str(buy_data["config"]["fee"]))
            sell_fee = sell_revenue * Decimal(str(sell_data["config"]["fee"]))
            
            gross_profit = sell_revenue - buy_cost
            net_profit = gross_profit - buy_fee - sell_fee
            
            return net_profit
            
        except Exception as e:
            logger.error(f"Error calculating BSC profit: {e}")
            return Decimal("0")
    
    async def _estimate_gas_cost(self) -> Decimal:
        """Estimate gas cost for cross arbitrage in USD"""
        try:
            # BSC gas is typically very low
            gas_price_gwei = 5  # 5 Gwei typical
            gas_used = 200000  # Two swaps
            
            # BNB price (mock)
            bnb_price_usd = Decimal("600")
            
            gas_cost_bnb = Decimal(str(gas_price_gwei)) * Decimal(str(gas_used)) / Decimal("1e9")
            gas_cost_usd = gas_cost_bnb * bnb_price_usd
            
            return gas_cost_usd
            
        except Exception:
            return Decimal("2.0")  # Fallback
    
    async def _estimate_liquidity(self, token_a: str, token_b: str) -> Decimal:
        """Estimate available liquidity"""
        # Mock liquidity estimation
        return Decimal("100000")  # $100K
    
    async def _estimate_price_impact(
        self, 
        amount: Decimal, 
        buy_data: Dict, 
        sell_data: Dict
    ) -> float:
        """Estimate price impact"""
        # Simple price impact estimation
        return 0.1  # 0.1%
    
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
            
            # Mock execution for now
            # This would build and execute actual swap transaction
            return {
                "success": True,
                "amount_out": amount_in * Decimal("0.998"),  # After fees
                "tx_hash": f"0x{'abc123' * 10}",
                "gas_cost": Decimal("1.0")
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
            
            # Mock execution for now
            return {
                "success": True,
                "amount_out": amount_in * Decimal("1.002"),  # Favorable rate
                "tx_hash": f"0x{'def456' * 10}",
                "gas_cost": Decimal("1.0")
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