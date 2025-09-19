import asyncio
import logging
from typing import Dict, List, Any, Optional, Callable
from decimal import Decimal
from datetime import datetime
import time
from dataclasses import dataclass

# Import shared models and interfaces
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from dex.shared.models.arbitrage_models import ArbitrageOpportunity, ExecutionResult, Token, DexPair
from dex.shared.interfaces.base_engine import BaseEngine

from .config import PolygonConfig
from .engine import PolygonEngine

logger = logging.getLogger(__name__)

@dataclass
class PipelineMetrics:
    """Pipeline performance metrics"""
    opportunities_scanned: int = 0
    opportunities_found: int = 0
    opportunities_executed: int = 0
    total_profit_usd: Decimal = Decimal("0")
    total_gas_spent_usd: Decimal = Decimal("0")
    success_rate: float = 0.0
    avg_execution_time: float = 0.0

class PolygonArbitragePipeline:
    """Advanced arbitrage pipeline for Polygon with opportunity scanning, processing, and execution"""
    
    def __init__(self, engine: PolygonEngine, config: PolygonConfig, telegram_callback: Optional[Callable] = None):
        self.engine = engine
        self.config = config
        self.telegram_callback = telegram_callback
        
        # Pipeline state
        self.is_running = False
        self.pipeline_task = None
        
        # Opportunity queues
        self.opportunity_queue = asyncio.Queue(maxsize=1000)
        self.execution_queue = asyncio.Queue(maxsize=100)
        
        # Pipeline components
        self.scanner_task = None
        self.processor_task = None
        self.executor_task = None
        
        # Performance metrics
        self.metrics = PipelineMetrics()
        self.start_time = None
        
        # Pipeline settings
        self.scan_interval = 2.0  # Scan every 2 seconds
        self.min_profit_usd = Decimal("10")  # Minimum $10 profit
        self.max_price_impact = Decimal("5")  # Max 5% price impact
        self.max_concurrent_executions = 3
        
        # DEX configurations for Polygon
        self.dex_configs = {
            "quickswap": {
                "router": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
                "factory": "0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32",
                "fee": Decimal("0.003")  # 0.3%
            },
            "sushiswap": {
                "router": "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
                "factory": "0xc35DADB65012eC5796536bD9864eD8773aBc74C4",
                "fee": Decimal("0.003")  # 0.3%
            },
            "uniswap_v3": {
                "router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
                "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
                "quoter": "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6",
                "fee_tiers": [500, 3000, 10000]  # 0.05%, 0.3%, 1%
            }
        }
        
        # Popular Polygon tokens
        self.base_tokens = {
            "WMATIC": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
            "USDC": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
            "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
            "DAI": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
            "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
            "WBTC": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6"
        }
        
    async def initialize(self) -> bool:
        """Initialize the arbitrage pipeline"""
        try:
            logger.info("Initializing Polygon Arbitrage Pipeline...")
            
            # Validate configuration
            if not await self._validate_config():
                return False
            
            # Initialize metrics
            self.metrics = PipelineMetrics()
            
            logger.info("Polygon Arbitrage Pipeline initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Polygon Arbitrage Pipeline: {e}")
            return False
    
    async def start(self):
        """Start the arbitrage pipeline"""
        if self.is_running:
            logger.warning("Polygon Arbitrage Pipeline is already running")
            return
        
        self.is_running = True
        self.start_time = time.time()
        
        # Start pipeline components
        self.scanner_task = asyncio.create_task(self._opportunity_scanner())
        self.processor_task = asyncio.create_task(self._opportunity_processor())
        self.executor_task = asyncio.create_task(self._opportunity_executor())
        
        logger.info("Polygon Arbitrage Pipeline started")
        
        # Send Telegram notification
        if self.telegram_callback:
            await self.telegram_callback(
                "🟣 Polygon Arbitrage Pipeline Started",
                f"Pipeline initialized with {len(self.dex_configs)} DEXs\n"
                f"Min profit: ${self.min_profit_usd}\n"
                f"Max price impact: {self.max_price_impact}%"
            )
    
    async def stop(self):
        """Stop the arbitrage pipeline"""
        self.is_running = False
        
        # Cancel all tasks
        tasks = [self.scanner_task, self.processor_task, self.executor_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        logger.info("Polygon Arbitrage Pipeline stopped")
        
        # Send final metrics via Telegram
        if self.telegram_callback:
            await self._send_final_metrics()
    
    async def _opportunity_scanner(self):
        """Continuously scan for arbitrage opportunities"""
        while self.is_running:
            try:
                start_time = time.time()
                
                # Scan cross-DEX opportunities
                opportunities = await self._scan_cross_dex_opportunities()
                
                # Add opportunities to queue
                for opportunity in opportunities:
                    try:
                        await self.opportunity_queue.put(opportunity)
                        self.metrics.opportunities_found += 1
                    except asyncio.QueueFull:
                        logger.warning("Opportunity queue is full, skipping opportunity")
                
                self.metrics.opportunities_scanned += len(opportunities)
                
                scan_time = time.time() - start_time
                logger.debug(f"Scanned {len(opportunities)} opportunities in {scan_time:.2f}s")
                
                # Wait before next scan
                await asyncio.sleep(self.scan_interval)
                
            except Exception as e:
                logger.error(f"Error in opportunity scanner: {e}")
                await asyncio.sleep(5)  # Wait before retry
    
    async def _opportunity_processor(self):
        """Process and validate opportunities from the queue"""
        while self.is_running:
            try:
                # Get opportunity from queue
                opportunity = await asyncio.wait_for(
                    self.opportunity_queue.get(), 
                    timeout=1.0
                )
                
                # Validate opportunity
                if await self._validate_opportunity(opportunity):
                    # Add to execution queue
                    try:
                        await self.execution_queue.put(opportunity)
                    except asyncio.QueueFull:
                        logger.warning("Execution queue is full, skipping opportunity")
                
                # Mark task as done
                self.opportunity_queue.task_done()
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in opportunity processor: {e}")
                await asyncio.sleep(1)
    
    async def _opportunity_executor(self):
        """Execute validated arbitrage opportunities"""
        active_executions = 0
        
        while self.is_running:
            try:
                if active_executions >= self.max_concurrent_executions:
                    await asyncio.sleep(0.1)
                    continue
                
                # Get opportunity from execution queue
                opportunity = await asyncio.wait_for(
                    self.execution_queue.get(),
                    timeout=1.0
                )
                
                # Execute opportunity asynchronously
                active_executions += 1
                asyncio.create_task(
                    self._execute_opportunity_with_cleanup(opportunity, active_executions)
                )
                
                # Mark task as done
                self.execution_queue.task_done()
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in opportunity executor: {e}")
                await asyncio.sleep(1)
    
    async def _execute_opportunity_with_cleanup(self, opportunity: ArbitrageOpportunity, execution_count: int):
        """Execute opportunity and handle cleanup"""
        try:
            result = await self._execute_opportunity(opportunity)
            
            # Update metrics
            self.metrics.opportunities_executed += 1
            if result.success:
                self.metrics.total_profit_usd += result.profit_usd
                self.metrics.total_gas_spent_usd += result.gas_cost_usd
            
            # Calculate success rate
            if self.metrics.opportunities_executed > 0:
                self.metrics.success_rate = (
                    sum(1 for _ in range(self.metrics.opportunities_executed) if result.success) /
                    self.metrics.opportunities_executed * 100
                )
            
            # Send Telegram notification for successful trades
            if result.success and self.telegram_callback:
                await self._send_execution_notification(opportunity, result)
                
        except Exception as e:
            logger.error(f"Error executing opportunity: {e}")
        finally:
            execution_count -= 1
    
    async def _scan_cross_dex_opportunities(self) -> List[ArbitrageOpportunity]:
        """Scan for cross-DEX arbitrage opportunities"""
        opportunities = []
        
        try:
            # Check all token pairs across DEXs
            for token_in_symbol, token_in_address in self.base_tokens.items():
                for token_out_symbol, token_out_address in self.base_tokens.items():
                    if token_in_address == token_out_address:
                        continue
                    
                    # Get prices from different DEXs
                    prices = await self._get_cross_dex_prices(token_in_address, token_out_address)
                    
                    # Find arbitrage opportunities
                    opportunity = await self._analyze_price_differences(
                        token_in_address, token_out_address, prices
                    )
                    
                    if opportunity:
                        opportunities.append(opportunity)
            
        except Exception as e:
            logger.error(f"Error scanning cross-DEX opportunities: {e}")
        
        return opportunities
    
    async def _get_cross_dex_prices(self, token_in: str, token_out: str) -> Dict[str, Decimal]:
        """Get prices from all DEXs for a token pair"""
        prices = {}
        amount_in = Decimal("1000000000000000000")  # 1 token (18 decimals)
        
        try:
            # QuickSwap price
            quickswap_price = await self._get_quickswap_price(token_in, token_out, amount_in)
            if quickswap_price > 0:
                prices["quickswap"] = quickswap_price
            
            # SushiSwap price
            sushiswap_price = await self._get_sushiswap_price(token_in, token_out, amount_in)
            if sushiswap_price > 0:
                prices["sushiswap"] = sushiswap_price
            
            # Uniswap V3 price (best fee tier)
            uniswap_price = await self._get_uniswap_v3_price(token_in, token_out, amount_in)
            if uniswap_price > 0:
                prices["uniswap_v3"] = uniswap_price
                
        except Exception as e:
            logger.error(f"Error getting cross-DEX prices: {e}")
        
        return prices
    
    async def _get_quickswap_price(self, token_in: str, token_out: str, amount_in: Decimal) -> Decimal:
        """Get price from QuickSwap"""
        try:
            # Use the engine's existing cross arbitrage functionality
            if hasattr(self.engine, 'cross_arbitrage'):
                price = await self.engine.cross_arbitrage._get_quickswap_price(token_in, token_out, amount_in)
                return price
            return Decimal("0")
        except Exception as e:
            logger.error(f"Error getting QuickSwap price: {e}")
            return Decimal("0")
    
    async def _get_sushiswap_price(self, token_in: str, token_out: str, amount_in: Decimal) -> Decimal:
        """Get price from SushiSwap"""
        try:
            # Use the engine's existing cross arbitrage functionality
            if hasattr(self.engine, 'cross_arbitrage'):
                price = await self.engine.cross_arbitrage._get_sushiswap_price(token_in, token_out, amount_in)
                return price
            return Decimal("0")
        except Exception as e:
            logger.error(f"Error getting SushiSwap price: {e}")
            return Decimal("0")
    
    async def _get_uniswap_v3_price(self, token_in: str, token_out: str, amount_in: Decimal) -> Decimal:
        """Get best price from Uniswap V3 across fee tiers"""
        try:
            # Use the engine's existing cross arbitrage functionality
            if hasattr(self.engine, 'cross_arbitrage'):
                price = await self.engine.cross_arbitrage._get_uniswap_v3_price(token_in, token_out, amount_in)
                return price
            return Decimal("0")
        except Exception as e:
            logger.error(f"Error getting Uniswap V3 price: {e}")
            return Decimal("0")
    
    async def _analyze_price_differences(self, token_in: str, token_out: str, 
                                       prices: Dict[str, Decimal]) -> Optional[ArbitrageOpportunity]:
        """Analyze price differences to find arbitrage opportunities"""
        try:
            if len(prices) < 2:
                return None
            
            # Find best buy and sell prices
            sorted_prices = sorted(prices.items(), key=lambda x: x[1])
            buy_dex, buy_price = sorted_prices[0]  # Lowest price (best buy)
            sell_dex, sell_price = sorted_prices[-1]  # Highest price (best sell)
            
            # Calculate potential profit
            price_diff = sell_price - buy_price
            profit_percentage = (price_diff / buy_price) * Decimal("100")
            
            # Check if profitable after fees
            total_fees = self.dex_configs[buy_dex]["fee"] + self.dex_configs[sell_dex]["fee"]
            net_profit_percentage = profit_percentage - (total_fees * Decimal("100"))
            
            if net_profit_percentage < Decimal("0.5"):  # Minimum 0.5% profit
                return None
            
            # Estimate profit in USD
            amount_in = Decimal("1000000000000000000")  # 1 token
            profit_amount = amount_in * (net_profit_percentage / Decimal("100"))
            profit_usd = await self._estimate_profit_usd(token_out, profit_amount)
            
            if profit_usd < self.min_profit_usd:
                return None
            
            # Create opportunity
            opportunity = ArbitrageOpportunity(
                token_in=token_in,
                token_out=token_out,
                amount_in=amount_in,
                buy_dex=buy_dex,
                sell_dex=sell_dex,
                buy_price=buy_price,
                sell_price=sell_price,
                profit_usd=profit_usd,
                profit_percentage=float(net_profit_percentage),
                timestamp=datetime.now()
            )
            
            return opportunity
            
        except Exception as e:
            logger.error(f"Error analyzing price differences: {e}")
            return None
    
    async def _validate_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        """Validate an arbitrage opportunity before execution"""
        try:
            # Check if opportunity is still valid (prices haven't changed too much)
            current_prices = await self._get_cross_dex_prices(
                opportunity.token_in, opportunity.token_out
            )
            
            if not current_prices:
                return False
            
            # Check if the price difference still exists
            buy_price = current_prices.get(opportunity.buy_dex, Decimal("0"))
            sell_price = current_prices.get(opportunity.sell_dex, Decimal("0"))
            
            if buy_price == 0 or sell_price == 0:
                return False
            
            # Calculate current profit
            price_diff = sell_price - buy_price
            current_profit_percentage = (price_diff / buy_price) * Decimal("100")
            
            # Check if still profitable (allow some slippage)
            min_profit_threshold = Decimal("0.3")  # 0.3% minimum
            if current_profit_percentage < min_profit_threshold:
                return False
            
            # Check price impact
            price_impact = await self._estimate_price_impact(opportunity)
            if price_impact > self.max_price_impact:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating opportunity: {e}")
            return False
    
    async def _execute_opportunity(self, opportunity: ArbitrageOpportunity) -> ExecutionResult:
        """Execute an arbitrage opportunity"""
        try:
            start_time = time.time()
            
            # Execute the arbitrage using the engine
            if hasattr(self.engine, 'cross_arbitrage'):
                result = await self.engine.cross_arbitrage.execute_arbitrage(
                    opportunity.token_in,
                    opportunity.token_out,
                    opportunity.amount_in,
                    opportunity.buy_dex,
                    opportunity.sell_dex
                )
                
                execution_time = time.time() - start_time
                
                # Update average execution time
                if self.metrics.opportunities_executed > 0:
                    self.metrics.avg_execution_time = (
                        (self.metrics.avg_execution_time * (self.metrics.opportunities_executed - 1) + execution_time) /
                        self.metrics.opportunities_executed
                    )
                else:
                    self.metrics.avg_execution_time = execution_time
                
                return result
            else:
                return ExecutionResult(
                    success=False,
                    error="Cross arbitrage engine not available",
                    profit_usd=Decimal("0"),
                    gas_cost_usd=Decimal("0")
                )
                
        except Exception as e:
            logger.error(f"Error executing opportunity: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
                profit_usd=Decimal("0"),
                gas_cost_usd=Decimal("0")
            )
    
    async def _estimate_profit_usd(self, token_address: str, amount: Decimal) -> Decimal:
        """Estimate profit in USD for a token amount"""
        try:
            # Get token price in USD (simplified implementation)
            # In production, you'd use a price oracle
            token_prices = {
                "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270": Decimal("0.8"),   # WMATIC
                "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174": Decimal("1.0"),   # USDC
                "0xc2132D05D31c914a87C6611C10748AEb04B58e8F": Decimal("1.0"),   # USDT
                "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063": Decimal("1.0"),   # DAI
                "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619": Decimal("2500"), # WETH
                "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6": Decimal("45000") # WBTC
            }
            
            token_price = token_prices.get(token_address, Decimal("1"))
            return (amount / Decimal("1000000000000000000")) * token_price
            
        except Exception as e:
            logger.error(f"Error estimating profit USD: {e}")
            return Decimal("0")
    
    async def _estimate_price_impact(self, opportunity: ArbitrageOpportunity) -> Decimal:
        """Estimate price impact for an opportunity"""
        try:
            # Simplified price impact calculation
            # In production, you'd calculate based on liquidity pools
            return Decimal("1.0")  # 1% default estimate
            
        except Exception as e:
            logger.error(f"Error estimating price impact: {e}")
            return Decimal("100")  # High impact on error
    
    async def _validate_config(self) -> bool:
        """Validate pipeline configuration"""
        try:
            # Check if engine is properly initialized
            if not self.engine:
                logger.error("Engine not provided")
                return False
            
            # Check DEX configurations
            for dex_name, config in self.dex_configs.items():
                if not config.get("router") or not config.get("factory"):
                    logger.error(f"Invalid configuration for {dex_name}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating config: {e}")
            return False
    
    async def _send_execution_notification(self, opportunity: ArbitrageOpportunity, result: ExecutionResult):
        """Send Telegram notification for successful execution"""
        try:
            if not self.telegram_callback:
                return
            
            message = (
                f"🟣 Polygon Arbitrage Executed!\n\n"
                f"💰 Profit: ${result.profit_usd:.2f}\n"
                f"⛽ Gas Cost: ${result.gas_cost_usd:.2f}\n"
                f"📊 Net Profit: ${result.profit_usd - result.gas_cost_usd:.2f}\n\n"
                f"🔄 Route: {opportunity.buy_dex} → {opportunity.sell_dex}\n"
                f"📈 Profit %: {opportunity.profit_percentage:.2f}%\n"
                f"⏱️ Execution Time: {self.metrics.avg_execution_time:.2f}s"
            )
            
            await self.telegram_callback("Polygon Arbitrage Success", message)
            
        except Exception as e:
            logger.error(f"Error sending execution notification: {e}")
    
    async def _send_final_metrics(self):
        """Send final pipeline metrics via Telegram"""
        try:
            if not self.telegram_callback:
                return
            
            runtime = time.time() - self.start_time if self.start_time else 0
            
            message = (
                f"🟣 Polygon Pipeline Stopped\n\n"
                f"📊 Final Metrics:\n"
                f"• Runtime: {runtime/3600:.1f} hours\n"
                f"• Opportunities Scanned: {self.metrics.opportunities_scanned}\n"
                f"• Opportunities Found: {self.metrics.opportunities_found}\n"
                f"• Opportunities Executed: {self.metrics.opportunities_executed}\n"
                f"• Success Rate: {self.metrics.success_rate:.1f}%\n"
                f"• Total Profit: ${self.metrics.total_profit_usd:.2f}\n"
                f"• Total Gas Spent: ${self.metrics.total_gas_spent_usd:.2f}\n"
                f"• Net Profit: ${self.metrics.total_profit_usd - self.metrics.total_gas_spent_usd:.2f}\n"
                f"• Avg Execution Time: {self.metrics.avg_execution_time:.2f}s"
            )
            
            await self.telegram_callback("Polygon Pipeline Report", message)
            
        except Exception as e:
            logger.error(f"Error sending final metrics: {e}")
    
    # Public interface methods
    def get_metrics(self) -> Dict[str, Any]:
        """Get current pipeline metrics"""
        runtime = time.time() - self.start_time if self.start_time else 0
        
        return {
            "is_running": self.is_running,
            "runtime_hours": runtime / 3600,
            "opportunities_scanned": self.metrics.opportunities_scanned,
            "opportunities_found": self.metrics.opportunities_found,
            "opportunities_executed": self.metrics.opportunities_executed,
            "success_rate": self.metrics.success_rate,
            "total_profit_usd": float(self.metrics.total_profit_usd),
            "total_gas_spent_usd": float(self.metrics.total_gas_spent_usd),
            "net_profit_usd": float(self.metrics.total_profit_usd - self.metrics.total_gas_spent_usd),
            "avg_execution_time": self.metrics.avg_execution_time,
            "queue_sizes": {
                "opportunity_queue": self.opportunity_queue.qsize(),
                "execution_queue": self.execution_queue.qsize()
            }
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get pipeline status"""
        return {
            "is_running": self.is_running,
            "components": {
                "scanner": self.scanner_task is not None and not self.scanner_task.done(),
                "processor": self.processor_task is not None and not self.processor_task.done(),
                "executor": self.executor_task is not None and not self.executor_task.done()
            },
            "settings": {
                "scan_interval": self.scan_interval,
                "min_profit_usd": float(self.min_profit_usd),
                "max_price_impact": float(self.max_price_impact),
                "max_concurrent_executions": self.max_concurrent_executions
            },
            "supported_dexs": list(self.dex_configs.keys())
        }
