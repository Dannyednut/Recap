import asyncio
import logging
import traceback
import time
from decimal import Decimal
from typing import Dict, List, Any, Optional
from datetime import datetime
import sys
import os

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from interfaces.base_engine import BaseArbitrageStrategy
from models.arbitrage_models import ArbitrageOpportunity, DexPair, Token

from .engine import EthereumEngine
from .config import EthereumConfig
from .protocols.uniswap_v2_adapter import UniswapV2Adapter
from .protocols.uniswap_v3_adapter import UniswapV3Adapter

logger = logging.getLogger(__name__)

class EthereumCrossArbitrage(BaseArbitrageStrategy):
    """Cross-DEX arbitrage between Uniswap V2/V3, SushiSwap, etc. on Ethereum"""
    
    def __init__(self, engine: EthereumEngine, config: EthereumConfig):
        self.engine = engine
        self.config = config
        
        # Real protocol adapters
        self.uniswap_v2 = None
        self.uniswap_v3 = None
        self.sushiswap_v2 = None  # Uses same adapter as Uniswap V2 with different factory
        
        # Price cache following CEX pattern
        self.price_cache = {}  # dex_name -> {"token_pair": {"price": Decimal, "timestamp": float}}
        self.last_update = {}
        
        # Running state
        self.running = False
        
        # Monitoring configuration - Ethereum mainnet token addresses
        self.monitoring_pairs = [
            # Major pairs to monitor on Ethereum mainnet
            ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0xdAC17F958D2ee523a2206206994597C13D831ec7"),  # WETH/USDT
            ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0xA0b86a33E6417aeBaD06072F4b82BC47A1E28fEB"),  # WETH/USDC
        ]
        
        # Profit thresholds
        self.min_profit_threshold = Decimal("0.1")  # 0.1% minimum profit
        self.reconnect_delay = 30  # 30 seconds between price updates
        
    async def initialize(self):
        """Initialize DEX adapters and price feeds"""
        logger.info("Initializing Ethereum cross-arbitrage engine...")
        try:
            # Initialize real protocol adapters
            self.uniswap_v2 = UniswapV2Adapter(self.engine.w3)
            self.uniswap_v3 = UniswapV3Adapter(self.engine.w3)
            
            # SushiSwap uses same V2 interface with different factory address
            self.sushiswap_v2 = UniswapV2Adapter(self.engine.w3)
            self.sushiswap_v2.FACTORY_ADDRESS = "0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac"  # SushiSwap factory
            
            # Initialize price cache structure
            self.price_cache = {
                "uniswap_v2": {},
                "uniswap_v3": {},
                "sushiswap_v2": {}
            }
            
            logger.info("Cross-arbitrage adapters initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize cross-arbitrage: {e}")
            raise
    
    async def start_price_monitoring(self):
        """Start continuous price monitoring like CEX system"""
        logger.info("Starting cross-DEX price monitoring...")
        self.running = True
        
        tasks = []
        
        # Start price monitoring for each DEX
        tasks.append(asyncio.create_task(self._monitor_uniswap_v2_prices()))
        tasks.append(asyncio.create_task(self._monitor_uniswap_v3_prices()))
        tasks.append(asyncio.create_task(self._monitor_sushiswap_prices()))
        
        # Start opportunity detection loop
        tasks.append(asyncio.create_task(self._continuous_opportunity_detection()))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def scan_opportunities(self) -> List[ArbitrageOpportunity]:
        """Scan for cross-DEX arbitrage opportunities (used by service)"""
        opportunities = []
        
        try:
            # Analyze current cached prices for opportunities
            for token_a, token_b in self.monitoring_pairs:
                opportunity = await self._analyze_pair_opportunities(token_a, token_b)
                if opportunity:
                    opportunities.append(opportunity)
                    
        except Exception as e:
            logger.error(f"Error scanning cross-arbitrage opportunities: {e}")
        
        return opportunities
    
    async def _monitor_uniswap_v2_prices(self):
        """Monitor Uniswap V2 prices continuously"""
        while self.running:
            try:
                prices = await self.uniswap_v2.get_multiple_prices(self.monitoring_pairs)
                
                for pair_key, price in prices.items():
                    self.price_cache["uniswap_v2"][pair_key] = {
                        "price": price,
                        "timestamp": time.time()
                    }
                    
                logger.debug(f"Updated {len(prices)} Uniswap V2 prices")
                await asyncio.sleep(self.reconnect_delay)
                
            except Exception as e:
                logger.error(f"Error monitoring Uniswap V2 prices: {e}")
                await asyncio.sleep(self.reconnect_delay)
    
    async def _monitor_uniswap_v3_prices(self):
        """Monitor Uniswap V3 prices continuously"""
        while self.running:
            try:
                prices = await self.uniswap_v3.get_multiple_prices(self.monitoring_pairs)
                
                for pair_key, price in prices.items():
                    self.price_cache["uniswap_v3"][pair_key] = {
                        "price": price,
                        "timestamp": time.time()
                    }
                    
                logger.debug(f"Updated {len(prices)} Uniswap V3 prices")
                await asyncio.sleep(self.reconnect_delay)
                
            except Exception as e:
                logger.error(f"Error monitoring Uniswap V3 prices: {e}")
                await asyncio.sleep(self.reconnect_delay)
    
    async def _monitor_sushiswap_prices(self):
        """Monitor SushiSwap prices continuously"""
        while self.running:
            try:
                prices = await self.sushiswap_v2.get_multiple_prices(self.monitoring_pairs)
                
                for pair_key, price in prices.items():
                    self.price_cache["sushiswap_v2"][pair_key] = {
                        "price": price,
                        "timestamp": time.time()
                    }
                    
                logger.debug(f"Updated {len(prices)} SushiSwap prices")
                await asyncio.sleep(self.reconnect_delay)
                
            except Exception as e:
                logger.error(f"Error monitoring SushiSwap prices: {e}")
                await asyncio.sleep(self.reconnect_delay)
    
    async def _continuous_opportunity_detection(self):
        """Continuously analyze cached prices for arbitrage opportunities (like CEX system)"""
        while self.running:
            try:
                for token_a, token_b in self.monitoring_pairs:
                    opportunity = await self._analyze_pair_opportunities(token_a, token_b)
                    if opportunity:
                        # Apply same filtering as CEX system
                        now_ts = time.time()
                        opp_ts = opportunity.detected_at.timestamp() if hasattr(opportunity.detected_at, 'timestamp') else now_ts
                        
                        # Skip stale opportunities (10 seconds max age)
                        if now_ts - opp_ts > 10:
                            logger.debug("Skipping stale DEX opportunity")
                            continue
                        
                        # Profit check against threshold
                        if opportunity.profit_percentage < self.min_profit_threshold:
                            logger.debug("Skipping low-profit DEX opportunity")
                            continue
                        
                        logger.info(f"Cross-DEX Opportunity: {token_a[:8]}.../{token_b[:8]}... | Profit: {opportunity.profit_percentage:.3f}%")
                        
                        # Save opportunity to engine (same as CEX)
                        await self.engine.save_opportunity(opportunity, 'ArbitrageOpportunity')
                
                await asyncio.sleep(2)  # Same frequency as CEX system
                
            except Exception as e:
                logger.error(f"Error in continuous DEX opportunity detection: {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(10)
    
    async def calculate_profit(self, opportunity: ArbitrageOpportunity) -> Decimal:
        """Calculate potential profit including gas costs"""
        try:
            if not opportunity.buy_price or not opportunity.sell_price:
                return Decimal("0")
            
            # Calculate gross profit
            price_diff = opportunity.sell_price - opportunity.buy_price
            gross_profit_pct = (price_diff / opportunity.buy_price) * 100
            
            # Estimate gas costs
            gas_cost = await self._estimate_arbitrage_gas_cost()
            
            # Calculate net profit
            trade_size_usd = Decimal(str(self.config.MAX_TRADE_SIZE_ETH)) * opportunity.buy_price
            gross_profit_usd = trade_size_usd * (gross_profit_pct / 100)
            
            # Subtract gas costs
            net_profit_usd = gross_profit_usd - gas_cost
            
            return net_profit_usd
            
        except Exception as e:
            logger.error(f"Error calculating profit: {e}")
            return Decimal("0")
    
    async def _analyze_pair_opportunities(self, token_a: str, token_b: str) -> Optional[ArbitrageOpportunity]:
        """Analyze price differences for a token pair across DEXs"""
        try:
            pair_key = f"{token_a}/{token_b}"
            current_time = time.time()
            dex_prices = {}
            
            # Collect prices from all DEXs
            for dex_name, dex_cache in self.price_cache.items():
                if pair_key in dex_cache:
                    price_data = dex_cache[pair_key]
                    
                    # Skip stale prices (older than 2 minutes)
                    if current_time - price_data["timestamp"] < 120:
                        dex_prices[dex_name] = price_data["price"]
            
            if len(dex_prices) < 2:
                return None
            
            # Find best buy and sell prices
            min_price_dex = min(dex_prices.keys(), key=lambda x: dex_prices[x])
            max_price_dex = max(dex_prices.keys(), key=lambda x: dex_prices[x])
            
            min_price = dex_prices[min_price_dex]
            max_price = dex_prices[max_price_dex]
            
            # Calculate profit percentage
            if min_price <= 0:
                return None
            
            profit_pct = ((max_price - min_price) / min_price) * 100
            
            # Create opportunity if profitable
            if profit_pct > self.min_profit_threshold:
                # Estimate profit in USD
                gas_cost = await self._estimate_arbitrage_gas_cost()
                trade_size_usd = Decimal(str(self.config.MAX_TRADE_SIZE_ETH)) * min_price
                gross_profit_usd = trade_size_usd * (profit_pct / 100)
                net_profit_usd = gross_profit_usd - gas_cost
                
                # Create tokens (simplified)
                token_a_obj = Token(address=token_a, symbol="TokenA", decimals=18, name="Token A")
                token_b_obj = Token(address=token_b, symbol="TokenB", decimals=18, name="Token B")
                
                # Create DexPair objects
                buy_pair = DexPair(
                    address="",  # Pool address would be fetched from adapter
                    token_a=token_a_obj,
                    token_b=token_b_obj,
                    dex_name=min_price_dex,
                    protocol_version="v2" if "v2" in min_price_dex else "v3"
                )
                
                sell_pair = DexPair(
                    address="",
                    token_a=token_a_obj,
                    token_b=token_b_obj,
                    dex_name=max_price_dex,
                    protocol_version="v2" if "v2" in max_price_dex else "v3"
                )
                
                opportunity = ArbitrageOpportunity(
                    opportunity_id=f"cross_{token_a[:8]}_{token_b[:8]}_{int(current_time)}",
                    strategy_type="cross",
                    chain="ethereum",
                    profit_percentage=profit_pct,
                    profit_amount_usd=gross_profit_usd,
                    gas_cost_usd=gas_cost,
                    net_profit_usd=net_profit_usd,
                    detected_at=datetime.now(),
                    buy_pair=buy_pair,
                    sell_pair=sell_pair,
                    buy_price=min_price,
                    sell_price=max_price
                )
                
                return opportunity
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing pair opportunities: {e}")
            return None
    
    async def _estimate_arbitrage_gas_cost(self) -> Decimal:
        """Estimate gas cost for arbitrage transaction"""
        try:
            # Get current gas price
            gas_info = await self.engine.get_gas_price()
            
            if gas_info["type"] == "eip1559":
                gas_price = gas_info["maxFeePerGas"]
            else:
                gas_price = gas_info["gasPrice"]
            
            # Estimate gas usage for cross-DEX arbitrage
            estimated_gas = 300000  # Conservative estimate for DEX arbitrage
            
            # Calculate cost in ETH
            gas_cost_wei = gas_price * estimated_gas
            gas_cost_eth = Decimal(gas_cost_wei) / Decimal(10**18)
            
            # Convert to USD (simplified - using ETH price from monitoring pairs)
            eth_price_usd = await self._get_eth_price_usd()
            gas_cost_usd = gas_cost_eth * eth_price_usd
            
            return gas_cost_usd
            
        except Exception as e:
            logger.error(f"Error estimating gas cost: {e}")
            return Decimal("50")  # Fallback to $50 gas cost
    
    async def _get_eth_price_usd(self) -> Decimal:
        """Get ETH price in USD from monitoring pairs"""
        try:
            # Look for ETH/USDT or ETH/USDC price in cache
            for dex_cache in self.price_cache.values():
                for pair_key, price_data in dex_cache.items():
                    if "USDT" in pair_key or "USDC" in pair_key:
                        return price_data["price"]
            
            # Fallback price
            return Decimal("2000")  # $2000 ETH
            
        except Exception:
            return Decimal("2000")
    
    async def stop(self):
        """Stop price monitoring"""
        logger.info("Stopping cross-DEX price monitoring")
        self.running = False
    
    async def execute_arbitrage(self, opportunity: ArbitrageOpportunity) -> Dict[str, Any]:
        """Execute cross-DEX arbitrage with flash loan"""
        try:
            logger.info(f"Executing cross-arbitrage: {opportunity.opportunity_id}")
            
            # This would:
            # 1. Request flash loan
            # 2. Buy on cheaper DEX
            # 3. Sell on more expensive DEX 
            # 4. Repay flash loan
            # 5. Keep profit
            
            # Placeholder implementation
            return {
                "status": "success",
                "tx_hash": "0x123...",
                "profit_realized": "0.5",
                "gas_used": 300000
            }
            
        except Exception as e:
            logger.error(f"Error executing arbitrage: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }
    
