import asyncio
import logging
from typing import Dict, List, Any, Optional
from decimal import Decimal

# Import shared models
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from dex.shared.models.arbitrage_models import Token, DexPair, SwapQuote

from .pancakeswap_adapter import PancakeSwapV2Adapter, PancakeSwapV3Adapter
from .biswap_adapter import BiswapAdapter, ApeSwapAdapter

logger = logging.getLogger(__name__)

class BSCProtocolManager:
    """Manages all BSC DEX protocol adapters"""
    
    def __init__(self, engine, config):
        self.engine = engine
        self.config = config
        
        # Initialize protocol adapters
        self.adapters = {
            "pancakeswap_v2": PancakeSwapV2Adapter(engine, config),
            "pancakeswap_v3": PancakeSwapV3Adapter(engine, config),
            "biswap": BiswapAdapter(engine, config),
            "apeswap": ApeSwapAdapter(engine, config)
        }
        
        # Protocol priorities (for routing optimization)
        self.protocol_priorities = {
            "pancakeswap_v2": 1,  # Highest liquidity
            "pancakeswap_v3": 2,  # Good for large trades
            "biswap": 3,          # Lower fees
            "apeswap": 4          # Alternative option
        }
        
        self.is_initialized = False
    
    async def initialize(self) -> bool:
        """Initialize all protocol adapters"""
        try:
            logger.info("Initializing BSC Protocol Manager...")
            
            # Test connectivity to each protocol
            for name, adapter in self.adapters.items():
                try:
                    # Test basic functionality
                    info = adapter.get_protocol_info()
                    logger.info(f"Initialized {name}: {info['name']}")
                except Exception as e:
                    logger.warning(f"Failed to initialize {name}: {e}")
            
            self.is_initialized = True
            logger.info("BSC Protocol Manager initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize BSC Protocol Manager: {e}")
            return False
    
    async def get_best_quote(self, amount_in: Decimal, token_in: str, token_out: str) -> Optional[SwapQuote]:
        """Get the best quote across all protocols"""
        try:
            quotes = []
            
            # Get quotes from all adapters
            for name, adapter in self.adapters.items():
                try:
                    quote = await adapter.get_quote(amount_in, token_in, token_out)
                    if quote.amount_out > 0:
                        quotes.append(quote)
                except Exception as e:
                    logger.warning(f"Failed to get quote from {name}: {e}")
            
            if not quotes:
                return None
            
            # Find best quote (highest output after considering gas costs)
            best_quote = max(quotes, key=lambda q: q.amount_out - q.gas_cost)
            
            return best_quote
            
        except Exception as e:
            logger.error(f"Error getting best quote: {e}")
            return None
    
    async def get_all_quotes(self, amount_in: Decimal, token_in: str, token_out: str) -> List[SwapQuote]:
        """Get quotes from all protocols"""
        try:
            quotes = []
            
            # Get quotes from all adapters
            tasks = []
            for name, adapter in self.adapters.items():
                task = asyncio.create_task(adapter.get_quote(amount_in, token_in, token_out))
                tasks.append((name, task))
            
            # Wait for all quotes
            for name, task in tasks:
                try:
                    quote = await task
                    if quote.amount_out > 0:
                        quotes.append(quote)
                except Exception as e:
                    logger.warning(f"Failed to get quote from {name}: {e}")
            
            # Sort by output amount (descending)
            quotes.sort(key=lambda q: q.amount_out, reverse=True)
            
            return quotes
            
        except Exception as e:
            logger.error(f"Error getting all quotes: {e}")
            return []
    
    async def execute_best_swap(self, amount_in: Decimal, min_amount_out: Decimal, 
                               token_in: str, token_out: str, to_address: str) -> Dict[str, Any]:
        """Execute swap on the protocol with best quote"""
        try:
            # Get best quote
            best_quote = await self.get_best_quote(amount_in, token_in, token_out)
            if not best_quote:
                return {
                    "success": False,
                    "error": "No viable quotes found"
                }
            
            # Find the adapter for the best protocol
            adapter = None
            for name, adp in self.adapters.items():
                if adp.protocol_name == best_quote.protocol:
                    adapter = adp
                    break
            
            if not adapter:
                return {
                    "success": False,
                    "error": f"Adapter not found for protocol: {best_quote.protocol}"
                }
            
            # Execute the swap
            result = await adapter.execute_swap(
                amount_in, min_amount_out, token_in, token_out, to_address
            )
            
            # Add quote information to result
            result["quote"] = {
                "protocol": best_quote.protocol,
                "amount_out": float(best_quote.amount_out),
                "price_impact": float(best_quote.price_impact),
                "gas_cost": float(best_quote.gas_cost)
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing best swap: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_aggregated_liquidity(self, token0: str, token1: str) -> Dict[str, Any]:
        """Get aggregated liquidity across all protocols"""
        try:
            total_liquidity_usd = Decimal("0")
            protocol_liquidity = {}
            
            # Get liquidity from all protocols
            for name, adapter in self.adapters.items():
                try:
                    liquidity_info = await adapter.get_liquidity_info(token0, token1)
                    liquidity_usd = Decimal(str(liquidity_info.get("liquidity_usd", 0)))
                    
                    if liquidity_usd > 0:
                        protocol_liquidity[name] = liquidity_info
                        total_liquidity_usd += liquidity_usd
                        
                except Exception as e:
                    logger.warning(f"Failed to get liquidity from {name}: {e}")
            
            return {
                "total_liquidity_usd": float(total_liquidity_usd),
                "protocol_breakdown": protocol_liquidity,
                "available_protocols": len(protocol_liquidity)
            }
            
        except Exception as e:
            logger.error(f"Error getting aggregated liquidity: {e}")
            return {
                "total_liquidity_usd": 0,
                "protocol_breakdown": {},
                "available_protocols": 0
            }
    
    async def find_arbitrage_opportunities(self, token_in: str, token_out: str, 
                                         amount_in: Decimal) -> List[Dict[str, Any]]:
        """Find arbitrage opportunities between protocols"""
        try:
            quotes = await self.get_all_quotes(amount_in, token_in, token_out)
            
            if len(quotes) < 2:
                return []
            
            opportunities = []
            
            # Compare all pairs of quotes
            for i in range(len(quotes)):
                for j in range(i + 1, len(quotes)):
                    quote1, quote2 = quotes[i], quotes[j]
                    
                    # Calculate potential profit
                    price_diff = abs(quote1.amount_out - quote2.amount_out)
                    total_gas_cost = quote1.gas_cost + quote2.gas_cost
                    
                    if price_diff > total_gas_cost:
                        profit = price_diff - total_gas_cost
                        
                        opportunities.append({
                            "buy_protocol": quote2.protocol if quote1.amount_out > quote2.amount_out else quote1.protocol,
                            "sell_protocol": quote1.protocol if quote1.amount_out > quote2.amount_out else quote2.protocol,
                            "profit_usd": float(profit),
                            "price_difference": float(price_diff),
                            "total_gas_cost": float(total_gas_cost),
                            "buy_quote": quote2 if quote1.amount_out > quote2.amount_out else quote1,
                            "sell_quote": quote1 if quote1.amount_out > quote2.amount_out else quote2
                        })
            
            # Sort by profit (descending)
            opportunities.sort(key=lambda x: x["profit_usd"], reverse=True)
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Error finding arbitrage opportunities: {e}")
            return []
    
    async def get_protocol_status(self) -> Dict[str, Any]:
        """Get status of all protocols"""
        try:
            status = {}
            
            for name, adapter in self.adapters.items():
                try:
                    # Test basic functionality
                    info = adapter.get_protocol_info()
                    
                    # Test a simple quote (WBNB -> BUSD)
                    wbnb = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
                    busd = "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56"
                    
                    quote = await adapter.get_quote(Decimal("1000000000000000000"), wbnb, busd)  # 1 WBNB
                    
                    status[name] = {
                        "status": "active" if quote.amount_out > 0 else "inactive",
                        "protocol_info": info,
                        "test_quote_output": float(quote.amount_out),
                        "last_checked": asyncio.get_event_loop().time()
                    }
                    
                except Exception as e:
                    status[name] = {
                        "status": "error",
                        "error": str(e),
                        "last_checked": asyncio.get_event_loop().time()
                    }
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting protocol status: {e}")
            return {}
    
    def get_supported_protocols(self) -> List[str]:
        """Get list of supported protocol names"""
        return list(self.adapters.keys())
    
    def get_adapter(self, protocol_name: str) -> Optional[Any]:
        """Get specific protocol adapter"""
        return self.adapters.get(protocol_name)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get protocol manager statistics"""
        return {
            "total_protocols": len(self.adapters),
            "supported_protocols": list(self.adapters.keys()),
            "is_initialized": self.is_initialized,
            "protocol_priorities": self.protocol_priorities
        }
