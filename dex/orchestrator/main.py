import asyncio
import logging
from typing import Dict, List, Any, Optional
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum
import json

# Shared imports
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from models.arbitrage_models import ArbitrageOpportunity, ExecutionResult, CrossChainOpportunity

# Microservice imports
from ..ethereum_service.arbitrage import EthereumArbitrageService
from .service_registry import ServiceRegistry
from .opportunity_aggregator import OpportunityAggregator
from .execution_coordinator import ExecutionCoordinator
from .risk_manager import RiskManager

logger = logging.getLogger(__name__)

class ChainStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive" 
    MAINTENANCE = "maintenance"
    ERROR = "error"

@dataclass
class SystemHealth:
    overall_status: str
    active_chains: List[str]
    inactive_chains: List[str]
    total_opportunities: int
    execution_success_rate: float
    last_updated: str

class DEXArbitrageOrchestrator:
    """Main orchestrator for multi-chain DEX arbitrage system"""
    
    def __init__(self):
        self.service_registry = ServiceRegistry()
        self.opportunity_aggregator = OpportunityAggregator()
        self.execution_coordinator = ExecutionCoordinator()
        self.risk_manager = RiskManager()
        
        # Service instances
        self.blockchain_services: Dict[str, Any] = {}
        self.chain_status: Dict[str, ChainStatus] = {}
        
        # System state
        self.is_running = False
        self.execution_queue: List[ArbitrageOpportunity] = []
        self.active_executions: Dict[str, Any] = {}
        
        # Configuration
        self.config = {
            "max_concurrent_executions": 5,
            "min_profit_threshold_usd": 50.0,
            "max_position_size_usd": 10000.0,
            "execution_timeout": 300,  # 5 minutes
            "health_check_interval": 30  # seconds
        }
    
    async def initialize(self) -> None:
        """Initialize all blockchain services and components"""
        try:
            logger.info("Initializing DEX Arbitrage Orchestrator...")
            
            # Initialize components
            await self.service_registry.initialize()
            await self.opportunity_aggregator.initialize()
            await self.execution_coordinator.initialize()
            await self.risk_manager.initialize()
            
            # Register and initialize blockchain services
            await self._initialize_blockchain_services()
            
            # Start background tasks
            asyncio.create_task(self._opportunity_scanner())
            asyncio.create_task(self._execution_processor())
            asyncio.create_task(self._health_monitor())
            
            self.is_running = True
            logger.info("DEX Arbitrage Orchestrator initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize orchestrator: {e}")
            raise
    
    async def _initialize_blockchain_services(self) -> None:
        """Initialize all blockchain microservices"""
        services_to_init = [
            ("ethereum", EthereumArbitrageService),
            # Will add more services: BSC, Polygon, Solana
        ]
        
        for chain_name, service_class in services_to_init:
            try:
                logger.info(f"Initializing {chain_name} service...")
                service = service_class()
                await service.initialize()
                
                self.blockchain_services[chain_name] = service
                self.chain_status[chain_name] = ChainStatus.ACTIVE
                await self.service_registry.register_service(chain_name, service)
                
                logger.info(f"{chain_name} service initialized successfully")
                
            except Exception as e:
                logger.error(f"Failed to initialize {chain_name} service: {e}")
                self.chain_status[chain_name] = ChainStatus.ERROR
    
    async def _opportunity_scanner(self) -> None:
        """Continuously scan for arbitrage opportunities across all chains"""
        logger.info("Starting opportunity scanner...")
        
        while self.is_running:
            try:
                # Scan each active blockchain service
                all_opportunities = []
                
                for chain_name, service in self.blockchain_services.items():
                    if self.chain_status[chain_name] == ChainStatus.ACTIVE:
                        try:
                            # Get cross-exchange arbitrage opportunities
                            cross_opportunities = await service.cross_arbitrage.scan_opportunities()
                            
                            # Get triangular arbitrage opportunities  
                            triangular_opportunities = await service.triangular_arbitrage.scan_opportunities()
                            
                            all_opportunities.extend(cross_opportunities)
                            all_opportunities.extend(triangular_opportunities)
                            
                        except Exception as e:
                            logger.error(f"Error scanning {chain_name}: {e}")
                            self.chain_status[chain_name] = ChainStatus.ERROR
                
                # Aggregate and filter opportunities
                if all_opportunities:
                    filtered_opportunities = await self.opportunity_aggregator.process_opportunities(
                        all_opportunities
                    )
                    
                    # Add profitable opportunities to execution queue
                    for opportunity in filtered_opportunities:
                        if await self.risk_manager.validate_opportunity(opportunity):
                            self.execution_queue.append(opportunity)
                
                await asyncio.sleep(5)  # Scan every 5 seconds
                
            except Exception as e:
                logger.error(f"Error in opportunity scanner: {e}")
                await asyncio.sleep(10)
    
    async def _execution_processor(self) -> None:
        """Process execution queue and coordinate trades"""
        logger.info("Starting execution processor...")
        
        while self.is_running:
            try:
                # Process execution queue
                while (self.execution_queue and 
                       len(self.active_executions) < self.config["max_concurrent_executions"]):
                    
                    opportunity = self.execution_queue.pop(0)
                    
                    # Create execution task
                    execution_id = f"exec_{len(self.active_executions)}_{opportunity.id}"
                    execution_task = asyncio.create_task(
                        self._execute_opportunity(execution_id, opportunity)
                    )
                    
                    self.active_executions[execution_id] = {
                        "task": execution_task,
                        "opportunity": opportunity,
                        "start_time": asyncio.get_event_loop().time()
                    }
                
                # Clean up completed executions
                completed_executions = []
                for exec_id, execution in self.active_executions.items():
                    if execution["task"].done():
                        completed_executions.append(exec_id)
                
                for exec_id in completed_executions:
                    del self.active_executions[exec_id]
                
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in execution processor: {e}")
                await asyncio.sleep(5)
    
    async def _execute_opportunity(self, execution_id: str, opportunity: ArbitrageOpportunity) -> ExecutionResult:
        """Execute a single arbitrage opportunity"""
        try:
            logger.info(f"Executing opportunity {opportunity.id} ({execution_id})")
            
            # Get the appropriate service for execution
            service = self.blockchain_services.get(opportunity.chain)
            if not service:
                raise ValueError(f"No service available for chain: {opportunity.chain}")
            
            # Execute through coordination layer
            result = await self.execution_coordinator.execute_opportunity(
                service, opportunity
            )
            
            # Log result
            if result.success:
                logger.info(f"Successfully executed {execution_id}: Profit ${result.profit_usd}")
            else:
                logger.warning(f"Failed to execute {execution_id}: {result.error}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing opportunity {execution_id}: {e}")
            return ExecutionResult(
                opportunity_id=opportunity.id,
                success=False,
                profit_usd=Decimal("0"),
                gas_cost_usd=Decimal("0"),
                execution_time=0.0,
                error=str(e)
            )
    
    async def _health_monitor(self) -> None:
        """Monitor system health and service status"""
        logger.info("Starting health monitor...")
        
        while self.is_running:
            try:
                # Check each service health
                for chain_name, service in self.blockchain_services.items():
                    try:
                        # Ping service for health check
                        health = await service.get_health_status()
                        
                        if health.get("status") == "healthy":
                            if self.chain_status[chain_name] == ChainStatus.ERROR:
                                logger.info(f"{chain_name} service recovered")
                            self.chain_status[chain_name] = ChainStatus.ACTIVE
                        else:
                            self.chain_status[chain_name] = ChainStatus.ERROR
                            logger.warning(f"{chain_name} service unhealthy: {health}")
                            
                    except Exception as e:
                        logger.error(f"Health check failed for {chain_name}: {e}")
                        self.chain_status[chain_name] = ChainStatus.ERROR
                
                await asyncio.sleep(self.config["health_check_interval"])
                
            except Exception as e:
                logger.error(f"Error in health monitor: {e}")
                await asyncio.sleep(30)
    
    async def get_system_status(self) -> SystemHealth:
        """Get current system health and status"""
        active_chains = [
            chain for chain, status in self.chain_status.items() 
            if status == ChainStatus.ACTIVE
        ]
        
        inactive_chains = [
            chain for chain, status in self.chain_status.items() 
            if status != ChainStatus.ACTIVE
        ]
        
        return SystemHealth(
            overall_status="healthy" if active_chains else "degraded",
            active_chains=active_chains,
            inactive_chains=inactive_chains,
            total_opportunities=len(self.execution_queue),
            execution_success_rate=await self._calculate_success_rate(),
            last_updated=str(asyncio.get_event_loop().time())
        )
    
    async def _calculate_success_rate(self) -> float:
        """Calculate recent execution success rate"""
        # This would track execution history
        return 85.5  # Placeholder
    
    async def get_opportunities(self, chain: Optional[str] = None) -> List[ArbitrageOpportunity]:
        """Get current arbitrage opportunities"""
        opportunities = self.execution_queue.copy()
        
        if chain:
            opportunities = [op for op in opportunities if op.chain == chain]
        
        return opportunities
    
    async def force_execution(self, opportunity_id: str) -> ExecutionResult:
        """Force execute a specific opportunity"""
        opportunity = next(
            (op for op in self.execution_queue if op.id == opportunity_id), 
            None
        )
        
        if not opportunity:
            raise ValueError(f"Opportunity {opportunity_id} not found")
        
        # Remove from queue and execute immediately
        self.execution_queue.remove(opportunity)
        return await self._execute_opportunity(f"force_{opportunity_id}", opportunity)
    
    async def shutdown(self) -> None:
        """Gracefully shutdown the orchestrator"""
        logger.info("Shutting down DEX Arbitrage Orchestrator...")
        
        self.is_running = False
        
        # Wait for active executions to complete
        if self.active_executions:
            logger.info(f"Waiting for {len(self.active_executions)} active executions...")
            for execution in self.active_executions.values():
                try:
                    await asyncio.wait_for(execution["task"], timeout=30)
                except asyncio.TimeoutError:
                    execution["task"].cancel()
        
        # Shutdown blockchain services
        for chain_name, service in self.blockchain_services.items():
            try:
                await service.shutdown()
                logger.info(f"Shutdown {chain_name} service")
            except Exception as e:
                logger.error(f"Error shutting down {chain_name}: {e}")
        
        logger.info("DEX Arbitrage Orchestrator shutdown complete")

# Main entry point
async def main():
    """Main orchestrator entry point"""
    orchestrator = DEXArbitrageOrchestrator()
    
    try:
        await orchestrator.initialize()
        
        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Orchestrator error: {e}")
    finally:
        await orchestrator.shutdown()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())