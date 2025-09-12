import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import sys
import os

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from models.arbitrage_models import ArbitrageOpportunity, ExecutionResult

from .config import EthereumConfig
from .engine import EthereumEngine
from .cross_arbitrage import EthereumCrossArbitrage
from .triangular_arbitrage import EthereumTriangularArbitrage
from .mempool_monitor import EthereumMempoolMonitor
from .flashloan_engine import EthereumFlashLoanEngine
from .contract_executor import EthereumContractExecutor
from .protocols.uniswap_v2_adapter import UniswapV2Adapter
from .protocols.uniswap_v3_adapter import UniswapV3Adapter

logger = logging.getLogger(__name__)

class EthereumArbitrageService:
    """Main Ethereum arbitrage microservice orchestrator"""
    
    def __init__(self):
        self.config = EthereumConfig()
        
        # Core components
        self.engine = EthereumEngine(self.config)
        self.cross_arbitrage = EthereumCrossArbitrage(self.engine, self.config)
        self.triangular_arbitrage = EthereumTriangularArbitrage(self.engine, self.config)
        self.mempool_monitor = EthereumMempoolMonitor(self.engine, self.config)
        self.flashloan_engine = EthereumFlashLoanEngine(self.engine, self.config)
        self.contract_executor = EthereumContractExecutor(self.engine.w3, self.config)
        
        # Protocol adapters are initialized in cross_arbitrage component
        
        # State
        self.is_running = False
        self.active_opportunities = {}
        self.execution_locks = {}
        
    async def initialize(self):
        """Initialize all components"""
        try:
            logger.info("Initializing Ethereum arbitrage service...")
            
            # Validate configuration
            self.config.validate()
            
            # Initialize core components
            await self.engine.initialize()
            await self.cross_arbitrage.initialize()
            await self.triangular_arbitrage.initialize()
            await self.mempool_monitor.initialize()
            await self.flashloan_engine.initialize()
            await self.contract_executor.initialize()
            
            # Protocol adapters are initialized within cross_arbitrage component
            
            # Setup mempool opportunity callback
            self.mempool_monitor.add_opportunity_callback(self._handle_mempool_opportunity)
            
            logger.info("Ethereum arbitrage service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Ethereum service: {e}")
            raise
    
    async def start(self):
        """Start the arbitrage service"""
        try:
            if self.is_running:
                logger.warning("Service already running")
                return
            
            self.is_running = True
            logger.info("Starting Ethereum arbitrage service...")
            
            # Start background tasks
            tasks = [
                asyncio.create_task(self._opportunity_scanner()),
                asyncio.create_task(self._mempool_monitoring()),
                asyncio.create_task(self._health_monitor()),
                asyncio.create_task(self.cross_arbitrage.start_price_monitoring())
            ]
            
            # Wait for all tasks
            await asyncio.gather(*tasks)
            
        except Exception as e:
            logger.error(f"Error in Ethereum service: {e}")
            self.is_running = False
    
    async def stop(self):
        """Stop the arbitrage service"""
        logger.info("Stopping Ethereum arbitrage service...")
        self.is_running = False
        await self.mempool_monitor.stop_monitoring()
    
    async def _opportunity_scanner(self):
        """Main opportunity scanning loop"""
        while self.is_running:
            try:
                # Scan for cross-exchange arbitrage
                cross_opportunities = await self.cross_arbitrage.scan_opportunities()
                for opportunity in cross_opportunities:
                    await self._evaluate_opportunity(opportunity)
                
                # Scan for triangular arbitrage
                triangular_opportunities = await self.triangular_arbitrage.scan_opportunities()
                for opportunity in triangular_opportunities:
                    await self._evaluate_opportunity(opportunity)
                
                # Wait before next scan
                await asyncio.sleep(1)  # Scan every second
                
            except Exception as e:
                logger.error(f"Error in opportunity scanner: {e}")
                await asyncio.sleep(5)  # Wait longer on error
    
    async def _mempool_monitoring(self):
        """Start mempool monitoring"""
        try:
            if self.config.MEMPOOL_MONITOR_ENABLED:
                await self.mempool_monitor.start_monitoring()
        except Exception as e:
            logger.error(f"Error in mempool monitoring: {e}")
    
    async def _health_monitor(self):
        """Monitor service health"""
        while self.is_running:
            try:
                # Check blockchain connection
                block_number = await self.engine.get_block_number()
                logger.debug(f"Current block: {block_number}")
                
                # Check wallet balance
                if self.engine.wallet_address:
                    eth_balance = await self.engine.get_balance("ETH", self.engine.wallet_address)
                    logger.debug(f"ETH balance: {eth_balance}")
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(60)
    
    async def _evaluate_opportunity(self, opportunity: ArbitrageOpportunity):
        """Evaluate and potentially execute an opportunity"""
        try:
            # Skip if already being processed
            if opportunity.opportunity_id in self.execution_locks:
                return
            
            # Calculate detailed profit
            if opportunity.strategy_type == "cross":
                profit = await self.cross_arbitrage.calculate_profit(opportunity)
            elif opportunity.strategy_type == "triangular":
                profit = await self.triangular_arbitrage.calculate_profit(opportunity)
            else:
                return
            
            # Check if profitable after costs
            if profit <= 0:
                return
            
            logger.info(f"Profitable opportunity found: {opportunity.opportunity_id}, profit: ${profit}")
            
            # Execute if profitable
            await self._execute_opportunity(opportunity)
            
        except Exception as e:
            logger.error(f"Error evaluating opportunity {opportunity.opportunity_id}: {e}")
    
    async def _execute_opportunity(self, opportunity: ArbitrageOpportunity):
        """Execute an arbitrage opportunity"""
        try:
            # Acquire execution lock
            self.execution_locks[opportunity.opportunity_id] = asyncio.Lock()
            
            async with self.execution_locks[opportunity.opportunity_id]:
                logger.info(f"Executing opportunity: {opportunity.opportunity_id}")
                
                # Execute based on strategy type
                if opportunity.strategy_type == "cross":
                    result = await self.cross_arbitrage.execute_arbitrage(opportunity)
                elif opportunity.strategy_type == "triangular":
                    result = await self.triangular_arbitrage.execute_arbitrage(opportunity)
                elif opportunity.strategy_type == "mempool_backrun":
                    result = await self.mempool_monitor.execute_backrun(opportunity)
                else:
                    logger.warning(f"Unknown strategy type: {opportunity.strategy_type}")
                    return
                
                # Log result
                if result.get("status") == "success":
                    logger.info(f"Successfully executed {opportunity.opportunity_id}: {result}")
                else:
                    logger.error(f"Failed to execute {opportunity.opportunity_id}: {result}")
            
        except Exception as e:
            logger.error(f"Error executing opportunity {opportunity.opportunity_id}: {e}")
        finally:
            # Clean up lock
            if opportunity.opportunity_id in self.execution_locks:
                del self.execution_locks[opportunity.opportunity_id]
    
    async def _handle_mempool_opportunity(self, opportunity: ArbitrageOpportunity):
        """Handle mempool opportunity callback"""
        try:
            logger.info(f"Mempool opportunity detected: {opportunity.opportunity_id}")
            await self._evaluate_opportunity(opportunity)
        except Exception as e:
            logger.error(f"Error handling mempool opportunity: {e}")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get comprehensive service status"""
        try:
            # Get the actual connected chain ID from web3 connection
            actual_chain_id = await self.engine.w3.eth.chain_id if self.engine.w3 else self.config.CHAIN_ID
            
            # Get wallet balance if available
            eth_balance = None
            if self.engine.wallet_address and self.engine.w3:
                try:
                    eth_balance = await self.engine.get_balance("ETH", self.engine.wallet_address)
                except Exception as e:
                    logger.debug(f"Could not get wallet balance: {e}")
            
            # Get gas price information
            gas_info = None
            try:
                gas_info = await self.engine.get_gas_price()
            except Exception as e:
                logger.debug(f"Could not get gas price: {e}")
            
            return {
                "service": "ethereum_arbitrage",
                "status": "running" if self.is_running else "stopped",
                "chain_id": actual_chain_id,
                "config_chain_id": self.config.CHAIN_ID,
                "wallet_address": self.engine.wallet_address,
                "wallet_balance_eth": float(eth_balance) if eth_balance else None,
                "block_number": await self.engine.get_block_number() if self.engine.w3 else 0,
                "active_opportunities": len(self.active_opportunities),
                "execution_locks": len(self.execution_locks),
                "mempool_monitoring": self.config.MEMPOOL_MONITOR_ENABLED,
                "price_monitoring_running": self.cross_arbitrage.running,
                "monitoring_pairs_count": len(self.cross_arbitrage.monitoring_pairs),
                "gas_price": gas_info,
                "contract_executor": {
                    "initialized": hasattr(self.contract_executor, 'w3') and self.contract_executor.w3 is not None,
                    "chain_id": actual_chain_id
                },
                "components": {
                    "engine": "initialized" if self.engine.w3 else "not_initialized",
                    "cross_arbitrage": "running" if self.cross_arbitrage.running else "stopped",
                    "triangular_arbitrage": "initialized",
                    "mempool_monitor": "enabled" if self.config.MEMPOOL_MONITOR_ENABLED else "disabled",
                    "flashloan_engine": "initialized",
                    "contract_executor": "initialized"
                },
                "last_update": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return {"status": "error", "error": str(e)}

# Main entry point for the microservice
async def main():
    """Main entry point"""
    logging.basicConfig(level=logging.INFO)
    
    service = EthereumArbitrageService()
    
    try:
        await service.initialize()
        await service.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        await service.stop()

if __name__ == "__main__":
    asyncio.run(main())