import asyncio
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import time

logger = logging.getLogger(__name__)

class EVMPriceAggregator:
    """Unified price aggregation system for all EVM-compatible chains"""
    
    def __init__(self):
        self.price_cache = {}  # chain -> token_pair -> price_data
        self.cache_ttl = 30  # 30 seconds cache TTL
        self.supported_chains = ["ethereum", "bsc", "polygon"]
        self.chain_engines = {}  # Will be populated by services
        
    def register_chain_engine(self, chain: str, engine):
        """Register a blockchain engine for price fetching"""
        self.chain_engines[chain] = engine
        if chain not in self.price_cache:
            self.price_cache[chain] = {}
        logger.info(f"Registered {chain} engine for price aggregation")
    
    async def get_best_price(
        self, 
        token_a: str, 
        token_b: str, 
        amount: Decimal,
        operation: str = "buy"  # "buy" or "sell"
    ) -> Optional[Dict[str, Any]]:
        """Get best price across all chains and DEXes"""
        try:
            all_prices = []
            
            # Fetch prices from all registered chains
            for chain, engine in self.chain_engines.items():
                try:
                    chain_prices = await self._get_chain_prices(
                        chain, engine, token_a, token_b, amount
                    )
                    all_prices.extend(chain_prices)
                except Exception as e:
                    logger.debug(f"Error getting prices from {chain}: {e}")
                    continue
            
            if not all_prices:
                return None
            
            # Find best price based on operation
            if operation == "buy":
                # For buying, we want the lowest price
                best_price = min(all_prices, key=lambda x: x["price"])
            else:
                # For selling, we want the highest price
                best_price = max(all_prices, key=lambda x: x["price"])
            
            return best_price
            
        except Exception as e:
            logger.error(f"Error getting best price: {e}")
            return None
    
    async def get_cross_chain_opportunities(
        self,
        token_pairs: List[Tuple[str, str]],
        min_profit_threshold: Decimal = Decimal("0.5")
    ) -> List[Dict[str, Any]]:
        """Find arbitrage opportunities across different chains"""
        opportunities = []
        
        try:
            for token_a, token_b in token_pairs:
                # Get prices from all chains
                chain_prices = {}
                
                for chain, engine in self.chain_engines.items():
                    try:
                        prices = await self._get_chain_prices(
                            chain, engine, token_a, token_b, Decimal("1.0")
                        )
                        if prices:
                            # Get best price from this chain
                            best_buy = min(prices, key=lambda x: x["price"])
                            best_sell = max(prices, key=lambda x: x["price"])
                            
                            chain_prices[chain] = {
                                "buy": best_buy,
                                "sell": best_sell
                            }
                    except Exception as e:
                        logger.debug(f"Error getting {chain} prices: {e}")
                        continue
                
                # Find cross-chain opportunities
                if len(chain_prices) >= 2:
                    chains = list(chain_prices.keys())
                    
                    for i in range(len(chains)):
                        for j in range(i + 1, len(chains)):
                            chain_a, chain_b = chains[i], chains[j]
                            
                            # Check both directions
                            opportunities.extend(
                                self._analyze_cross_chain_pair(
                                    token_a, token_b, chain_a, chain_b,
                                    chain_prices[chain_a], chain_prices[chain_b],
                                    min_profit_threshold
                                )
                            )
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Error finding cross-chain opportunities: {e}")
            return []
    
    async def _get_chain_prices(
        self,
        chain: str,
        engine,
        token_a: str,
        token_b: str,
        amount: Decimal
    ) -> List[Dict[str, Any]]:
        """Get prices from a specific chain"""
        try:
            cache_key = f"{token_a}_{token_b}"
            current_time = time.time()
            
            # Check cache first
            if (cache_key in self.price_cache[chain] and 
                current_time - self.price_cache[chain][cache_key]["timestamp"] < self.cache_ttl):
                return self.price_cache[chain][cache_key]["prices"]
            
            # Fetch fresh prices
            prices = []
            
            if hasattr(engine, 'cross_arbitrage') and engine.cross_arbitrage:
                # Get prices from cross-arbitrage engine
                dex_prices = await engine.cross_arbitrage._get_prices_across_dexes(
                    token_a, token_b
                )
                
                for price_data in dex_prices:
                    prices.append({
                        "chain": chain,
                        "dex": price_data["dex"],
                        "price": price_data["price"],
                        "liquidity": await self._estimate_liquidity(
                            engine, token_a, token_b, price_data["dex"]
                        ),
                        "gas_cost": await self._estimate_gas_cost(engine),
                        "timestamp": current_time
                    })
            
            # Cache the results
            self.price_cache[chain][cache_key] = {
                "prices": prices,
                "timestamp": current_time
            }
            
            return prices
            
        except Exception as e:
            logger.debug(f"Error getting {chain} prices: {e}")
            return []
    
    def _analyze_cross_chain_pair(
        self,
        token_a: str,
        token_b: str,
        chain_a: str,
        chain_b: str,
        prices_a: Dict,
        prices_b: Dict,
        min_profit_threshold: Decimal
    ) -> List[Dict[str, Any]]:
        """Analyze cross-chain arbitrage opportunity between two chains"""
        opportunities = []
        
        try:
            # Opportunity 1: Buy on chain A, sell on chain B
            buy_price_a = prices_a["buy"]["price"]
            sell_price_b = prices_b["sell"]["price"]
            
            if sell_price_b > buy_price_a:
                profit_pct = ((sell_price_b - buy_price_a) / buy_price_a) * 100
                
                if profit_pct > min_profit_threshold:
                    opportunities.append({
                        "type": "cross_chain",
                        "token_a": token_a,
                        "token_b": token_b,
                        "buy_chain": chain_a,
                        "sell_chain": chain_b,
                        "buy_dex": prices_a["buy"]["dex"],
                        "sell_dex": prices_b["sell"]["dex"],
                        "buy_price": buy_price_a,
                        "sell_price": sell_price_b,
                        "profit_percentage": profit_pct,
                        "estimated_gas_cost": (
                            prices_a["buy"].get("gas_cost", Decimal("0")) +
                            prices_b["sell"].get("gas_cost", Decimal("0"))
                        ),
                        "timestamp": datetime.now()
                    })
            
            # Opportunity 2: Buy on chain B, sell on chain A
            buy_price_b = prices_b["buy"]["price"]
            sell_price_a = prices_a["sell"]["price"]
            
            if sell_price_a > buy_price_b:
                profit_pct = ((sell_price_a - buy_price_b) / buy_price_b) * 100
                
                if profit_pct > min_profit_threshold:
                    opportunities.append({
                        "type": "cross_chain",
                        "token_a": token_a,
                        "token_b": token_b,
                        "buy_chain": chain_b,
                        "sell_chain": chain_a,
                        "buy_dex": prices_b["buy"]["dex"],
                        "sell_dex": prices_a["sell"]["dex"],
                        "buy_price": buy_price_b,
                        "sell_price": sell_price_a,
                        "profit_percentage": profit_pct,
                        "estimated_gas_cost": (
                            prices_b["buy"].get("gas_cost", Decimal("0")) +
                            prices_a["sell"].get("gas_cost", Decimal("0"))
                        ),
                        "timestamp": datetime.now()
                    })
            
            return opportunities
            
        except Exception as e:
            logger.debug(f"Error analyzing cross-chain pair: {e}")
            return []
    
    async def _estimate_liquidity(
        self,
        engine,
        token_a: str,
        token_b: str,
        dex: str
    ) -> Decimal:
        """Estimate liquidity for a token pair on a DEX"""
        try:
            if hasattr(engine, 'cross_arbitrage') and engine.cross_arbitrage:
                return await engine.cross_arbitrage._estimate_liquidity(token_a, token_b)
            return Decimal("100000")  # Fallback
        except Exception:
            return Decimal("100000")  # Fallback
    
    async def _estimate_gas_cost(self, engine) -> Decimal:
        """Estimate gas cost for transactions on a chain"""
        try:
            if hasattr(engine, 'cross_arbitrage') and engine.cross_arbitrage:
                return await engine.cross_arbitrage._estimate_gas_cost()
            return Decimal("10")  # Fallback
        except Exception:
            return Decimal("10")  # Fallback
    
    async def get_price_comparison(
        self,
        token_a: str,
        token_b: str
    ) -> Dict[str, Any]:
        """Get comprehensive price comparison across all chains and DEXes"""
        try:
            comparison = {
                "token_pair": f"{token_a}/{token_b}",
                "chains": {},
                "best_buy": None,
                "best_sell": None,
                "price_spread": Decimal("0"),
                "timestamp": datetime.now()
            }
            
            all_prices = []
            
            # Collect prices from all chains
            for chain, engine in self.chain_engines.items():
                try:
                    chain_prices = await self._get_chain_prices(
                        chain, engine, token_a, token_b, Decimal("1.0")
                    )
                    
                    comparison["chains"][chain] = {
                        "dexes": chain_prices,
                        "best_buy": min(chain_prices, key=lambda x: x["price"]) if chain_prices else None,
                        "best_sell": max(chain_prices, key=lambda x: x["price"]) if chain_prices else None
                    }
                    
                    all_prices.extend(chain_prices)
                    
                except Exception as e:
                    logger.debug(f"Error getting {chain} comparison: {e}")
                    comparison["chains"][chain] = {"error": str(e)}
            
            # Find global best prices
            if all_prices:
                comparison["best_buy"] = min(all_prices, key=lambda x: x["price"])
                comparison["best_sell"] = max(all_prices, key=lambda x: x["price"])
                comparison["price_spread"] = (
                    comparison["best_sell"]["price"] - comparison["best_buy"]["price"]
                )
            
            return comparison
            
        except Exception as e:
            logger.error(f"Error creating price comparison: {e}")
            return {"error": str(e)}
    
    def clear_cache(self, chain: Optional[str] = None):
        """Clear price cache for specific chain or all chains"""
        if chain:
            if chain in self.price_cache:
                self.price_cache[chain].clear()
                logger.info(f"Cleared price cache for {chain}")
        else:
            self.price_cache.clear()
            logger.info("Cleared all price caches")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        stats = {
            "total_chains": len(self.chain_engines),
            "cache_ttl_seconds": self.cache_ttl,
            "chains": {}
        }
        
        for chain in self.supported_chains:
            if chain in self.price_cache:
                stats["chains"][chain] = {
                    "cached_pairs": len(self.price_cache[chain]),
                    "registered": chain in self.chain_engines
                }
        
        return stats

# Global price aggregator instance
price_aggregator = EVMPriceAggregator()
