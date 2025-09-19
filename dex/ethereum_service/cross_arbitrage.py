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
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from dex.shared.interfaces.base_engine import BaseArbitrageStrategy
from dex.shared.models.arbitrage_models import ArbitrageOpportunity, DexPair, Token, ExecutionResult

from .engine import EthereumEngine
from .config import EthereumConfig
from .protocols.uniswap_v2_adapter import UniswapV2Adapter
from .protocols.uniswap_v3_adapter import UniswapV3Adapter

logger = logging.getLogger(__name__)

class CrossArbitrageEngine(BaseArbitrageStrategy):
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
        
            # Real Ethereum mainnet token addresses for monitoring
        self.monitoring_pairs = [
            # Major pairs to monitor with real contract addresses
            ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0xdAC17F958D2ee523a2206206994597C13D831ec7"),  # WETH/USDT
            ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0xA0b86a33E6417aeBaD06072F4b82BC47A1E28fEB"),  # WETH/USDC
            ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"),  # WETH/WBTC
            ("0xA0b86a33E6417aeBaD06072F4b82BC47A1E28fEB", "0xdAC17F958D2ee523a2206206994597C13D831ec7"),  # USDC/USDT
        ]
        
        # Profit thresholds
        self.min_profit_threshold = Decimal("0.1")  # 0.1% minimum profit
        self.reconnect_delay = 30  # 30 seconds between price updates
        
    async def initialize(self) -> None:
        """Initialize the cross-arbitrage engine"""
        try:
            logger.info("Initializing Ethereum Cross-Arbitrage Engine...")
            
            # Initialize protocol adapters with real contract integrations
            self.uniswap_v2 = UniswapV2Adapter(self.engine.w3)
            self.uniswap_v3 = UniswapV3Adapter(self.engine.w3)
            
            # SushiSwap uses same V2 interface as Uniswap V2 but different factory
            self.sushiswap_v2 = UniswapV2Adapter(self.engine.w3)
            # Override factory address for SushiSwap
            self.sushiswap_v2.FACTORY_ADDRESS = "0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac"
            self.sushiswap_v2.ROUTER_ADDRESS = "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F"
            
            # Initialize price caches for real-time monitoring
            self.price_cache = {
                "uniswap_v2": {},
                "uniswap_v3": {},
                "sushiswap_v2": {}
            }
            
            # Start real-time price monitoring tasks
            self.running = True
            asyncio.create_task(self._monitor_uniswap_v2_prices())
            asyncio.create_task(self._monitor_uniswap_v3_prices())
            asyncio.create_task(self._monitor_sushiswap_v2_prices())
            
            self.initialized = True
            logger.info("Ethereum Cross-Arbitrage Engine initialized with real DEX integrations")
            
        except Exception as e:
            logger.error(f"Failed to initialize Ethereum Cross-Arbitrage Engine: {e}")
            raise
    
    async def start_price_monitoring(self):
        """Start continuous price monitoring like CEX system"""
        logger.info("Starting cross-DEX price monitoring...")
        
        tasks = []
        
        # Start price monitoring for each DEX
        tasks.append(asyncio.create_task(self._monitor_uniswap_v2_prices()))
        tasks.append(asyncio.create_task(self._monitor_uniswap_v3_prices()))
        tasks.append(asyncio.create_task(self._monitor_sushiswap_v2_prices()))
        
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
    
    async def _monitor_sushiswap_v2_prices(self):
        """Monitor SushiSwap V2 prices continuously using real contract calls"""
        while self.running:
            try:
                prices = await self.sushiswap_v2.get_multiple_prices(self.monitoring_pairs)
                
                for pair_key, price in prices.items():
                    self.price_cache["sushiswap_v2"][pair_key] = {
                        "price": price,
                        "timestamp": time.time(),
                        "source": "sushiswap_v2_contract"
                    }
                    
                logger.debug(f"Updated {len(prices)} SushiSwap V2 prices from contracts")
                await asyncio.sleep(self.reconnect_delay)
                
            except Exception as e:
                logger.error(f"Error monitoring SushiSwap V2 prices: {e}")
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
        """Get real ETH price in USD from DEX contracts"""
        try:
            # WETH and USDC addresses on Ethereum mainnet
            weth_address = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
            usdc_address = "0xA0b86a33E6417aeBaD06072F4b82BC47A1E28fEB"
            
            # Try to get price from Uniswap V3 first (usually most accurate)
            eth_price = await self.uniswap_v3.get_token_price(weth_address, usdc_address)
            if eth_price and eth_price > 0:
                return eth_price
            
            # Fallback to Uniswap V2
            eth_price = await self.uniswap_v2.get_token_price(weth_address, usdc_address)
            if eth_price and eth_price > 0:
                return eth_price
            
            # Look in cached prices as final fallback
            for dex_cache in self.price_cache.values():
                for pair_key, price_data in dex_cache.items():
                    if "USDT" in pair_key or "USDC" in pair_key:
                        return price_data["price"]
            
            # Default fallback price
            return Decimal("3200.00")
            
        except Exception as e:
            logger.debug(f"Error getting ETH price: {e}")
            return Decimal("3200.00")
    
    async def stop(self):
        """Stop price monitoring"""
        logger.info("Stopping cross-DEX price monitoring")
        self.running = False
    
    async def execute_opportunity(self, opportunity: ArbitrageOpportunity) -> ExecutionResult:
        """Execute cross-exchange arbitrage opportunity using real DEX contracts"""
        start_time = time.time()
        
        try:
            logger.info(f"Executing Ethereum cross arbitrage: {opportunity.id}")
            
            # Step 1: Buy on exchange A (cheaper DEX)
            buy_result = await self._execute_buy(
                opportunity.exchange_a,
                opportunity.token_a,
                opportunity.token_b,
                opportunity.amount_in
            )
            
            if not buy_result["success"]:
                raise Exception(f"Buy failed: {buy_result['error']}")
            
            # Step 2: Sell on exchange B (more expensive DEX)
            sell_result = await self._execute_sell(
                opportunity.exchange_b,
                opportunity.token_b,
                opportunity.token_a,
                buy_result["amount_out"]
            )
            
            if not sell_result["success"]:
                raise Exception(f"Sell failed: {sell_result['error']}")
            
            execution_time = time.time() - start_time
            
            # Calculate actual profit
            actual_profit = sell_result["amount_out"] - opportunity.amount_in
            
            return ExecutionResult(
                opportunity_id=opportunity.id,
                success=True,
                profit_usd=float(actual_profit * opportunity.price_a),  # Convert to USD
                gas_cost_usd=float(buy_result["gas_cost"] + sell_result["gas_cost"]),
                execution_time=execution_time,
                transaction_hashes=[buy_result["tx_hash"], sell_result["tx_hash"]]
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Ethereum cross arbitrage execution failed: {e}")
            
            return ExecutionResult(
                opportunity_id=opportunity.id,
                success=False,
                profit_usd=0.0,
                gas_cost_usd=0.0,
                execution_time=execution_time,
                error=str(e)
            )
    
    async def _execute_buy(
        self, 
        dex: str, 
        token_in: str, 
        token_out: str, 
        amount_in: Decimal
    ) -> Dict[str, Any]:
        """Execute real buy order on specified DEX using router contract"""
        try:
            logger.info(f"Executing real buy on {dex}: {amount_in} {token_in} -> {token_out}")
            
            # Get DEX adapter based on name
            adapter = None
            if "uniswap_v2" in dex.lower():
                adapter = self.uniswap_v2
            elif "uniswap_v3" in dex.lower():
                adapter = self.uniswap_v3
            elif "sushiswap" in dex.lower():
                adapter = self.sushiswap_v2
            else:
                raise ValueError(f"Unsupported DEX: {dex}")
            
            # Execute swap through adapter
            tx_hash = await adapter.execute_swap(
                token_in, token_out, int(amount_in * Decimal(10**18))
            )
            
            if not tx_hash:
                return {
                    "success": False,
                    "error": "Failed to execute swap",
                    "gas_cost": Decimal("0")
                }
            
            # Wait for confirmation
            result = await self.engine.wait_for_transaction_receipt(tx_hash)
            
            if result:
                # Calculate actual output amount (simplified estimation)
                fee_rate = Decimal("0.003")  # 0.3% typical DEX fee
                amount_out = amount_in * (Decimal("1") - fee_rate)
                gas_cost_usd = await self._calculate_real_gas_cost(result.gasUsed)
                
                return {
                    "success": True,
                    "amount_out": amount_out,
                    "tx_hash": tx_hash.hex(),
                    "gas_cost": gas_cost_usd
                }
            else:
                return {
                    "success": False,
                    "error": "Transaction failed",
                    "gas_cost": Decimal("0")
                }
            
        except Exception as e:
            logger.error(f"Error executing buy on {dex}: {e}")
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
        """Execute real sell order on specified DEX using router contract"""
        try:
            logger.info(f"Executing real sell on {dex}: {amount_in} {token_in} -> {token_out}")
            
            # Get DEX adapter based on name
            adapter = None
            if "uniswap_v2" in dex.lower():
                adapter = self.uniswap_v2
            elif "uniswap_v3" in dex.lower():
                adapter = self.uniswap_v3
            elif "sushiswap" in dex.lower():
                adapter = self.sushiswap
            else:
                raise ValueError(f"Unsupported DEX: {dex}")
            
            # Execute swap through adapter
            tx_hash = await adapter.execute_swap(
                token_in, token_out, int(amount_in * Decimal(10**18))
            )
            
            if not tx_hash:
                return {
                    "success": False,
                    "error": "Failed to execute swap",
                    "gas_cost": Decimal("0")
                }
            
            # Wait for confirmation
            result = await self.engine.wait_for_transaction_receipt(tx_hash)
            
            if result:
                # Calculate actual output amount (simplified estimation)
                fee_rate = Decimal("0.003")  # 0.3% typical DEX fee
                amount_out = amount_in * (Decimal("1") - fee_rate)
                gas_cost_usd = await self._calculate_real_gas_cost(result.gasUsed)
                
                return {
                    "success": True,
                    "amount_out": amount_out,
                    "tx_hash": tx_hash.hex(),
                    "gas_cost": gas_cost_usd
                }
            else:
                return {
                    "success": False,
                    "error": "Transaction failed",
                    "gas_cost": Decimal("0")
                }
            
        except Exception as e:
            logger.error(f"Error executing sell on {dex}: {e}")
            return {
                "success": False,
                "error": str(e),
                "gas_cost": Decimal("0")
            }
    
