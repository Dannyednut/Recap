import asyncio
import logging
from typing import Dict, Any, List, Optional, Set

from .chain_factory import ChainFactory
from .shared.models.chain_models import ChainConfig

logger = logging.getLogger(__name__)

class ArbitrageManager:
    """Manager for coordinating arbitrage across multiple chains"""
    
    def __init__(self, config):
        """Initialize the arbitrage manager"""
        # Handle both list of chains and config dictionary
        if isinstance(config, list):
            self.chains = config
            self.config = {'chains': config}
        else:
            self.config = config
            self.chains = config.get('chains', ['ethereum'])
        self.engines = {}
        self.cross_arbitrage_strategies = {}
        self.triangular_arbitrage_strategies = {}
        self.mempool_monitors = {}
        self.flashloan_engines = {}
        self.contract_executors = {}
        self.token_discovery_services = {}
        self.arbitrage_pipelines = {}
        self.active_chains = set()
        self.is_running = False
        self.stats = {}
    
    async def initialize(self) -> bool:
        """Initialize all components for each chain"""
        try:
            for chain_id in self.chains:
                chain_config = self.config.get(chain_id, {})
                
                # Create engine
                engine = ChainFactory.create_engine(chain_id, chain_config)
                if not engine:
                    logger.error(f"Failed to create engine for chain {chain_id}")
                    continue
                
                # Initialize engine
                if not await engine.initialize():
                    logger.error(f"Failed to initialize engine for chain {chain_id}")
                    continue
                
                self.engines[chain_id] = engine
                
                # Create and initialize token discovery service
                token_discovery = ChainFactory.create_token_discovery(chain_id, engine, chain_config)
                if token_discovery and await token_discovery.initialize():
                    self.token_discovery_services[chain_id] = token_discovery
                else:
                    logger.error(f"Failed to initialize token discovery for chain {chain_id}")
                    continue
                
                # Create and initialize flashloan engine
                flashloan_engine = ChainFactory.create_flashloan_engine(chain_id, engine, chain_config)
                if flashloan_engine and await flashloan_engine.initialize():
                    self.flashloan_engines[chain_id] = flashloan_engine
                else:
                    logger.error(f"Failed to initialize flashloan engine for chain {chain_id}")
                    continue
                
                # Create and initialize contract executor
                contract_executor = ChainFactory.create_contract_executor(chain_id, engine, chain_config)
                if contract_executor and await contract_executor.initialize():
                    self.contract_executors[chain_id] = contract_executor
                else:
                    logger.error(f"Failed to initialize contract executor for chain {chain_id}")
                    continue
                
                # Create and initialize cross arbitrage strategy
                cross_arbitrage = ChainFactory.create_arbitrage_strategy(
                    chain_id, "cross", engine, chain_config
                )
                if cross_arbitrage and await cross_arbitrage.initialize():
                    self.cross_arbitrage_strategies[chain_id] = cross_arbitrage
                else:
                    logger.error(f"Failed to initialize cross arbitrage for chain {chain_id}")
                    continue
                
                # Create and initialize triangular arbitrage strategy
                triangular_arbitrage = ChainFactory.create_arbitrage_strategy(
                    chain_id, "triangular", engine, chain_config
                )
                if triangular_arbitrage and await triangular_arbitrage.initialize():
                    self.triangular_arbitrage_strategies[chain_id] = triangular_arbitrage
                else:
                    logger.error(f"Failed to initialize triangular arbitrage for chain {chain_id}")
                    continue
                
                # Create and initialize mempool monitor
                mempool_monitor = ChainFactory.create_mempool_monitor(chain_id, engine, chain_config)
                if mempool_monitor and await mempool_monitor.initialize():
                    self.mempool_monitors[chain_id] = mempool_monitor
                else:
                    logger.error(f"Failed to initialize mempool monitor for chain {chain_id}")
                    # This is optional, so we can continue
                
                # Create and initialize arbitrage pipeline
                arbitrage_pipeline = ChainFactory.create_arbitrage_pipeline(
                    chain_id,
                    engine,
                    cross_arbitrage,
                    triangular_arbitrage,
                    mempool_monitor if chain_id in self.mempool_monitors else None,
                    flashloan_engine,
                    contract_executor,
                    token_discovery,
                    chain_config
                )
                if arbitrage_pipeline and await arbitrage_pipeline.initialize():
                    self.arbitrage_pipelines[chain_id] = arbitrage_pipeline
                else:
                    logger.error(f"Failed to initialize arbitrage pipeline for chain {chain_id}")
                    continue
                
                # Add to active chains
                self.active_chains.add(chain_id)
                logger.info(f"Successfully initialized chain {chain_id}")
            
            return len(self.active_chains) > 0
        
        except Exception as e:
            logger.error(f"Error initializing arbitrage manager: {e}")
            return False
    
    async def start(self) -> bool:
        """Start arbitrage on all active chains"""
        if self.is_running:
            logger.warning("Arbitrage manager is already running")
            return True
        
        try:
            for chain_id in self.active_chains:
                # Start token discovery service
                if chain_id in self.token_discovery_services:
                    await self.token_discovery_services[chain_id].start()
                
                # Start mempool monitor if available
                if chain_id in self.mempool_monitors:
                    await self.mempool_monitors[chain_id].start_monitoring()
                
                # Start arbitrage pipeline
                if chain_id in self.arbitrage_pipelines:
                    await self.arbitrage_pipelines[chain_id].start()
            
            self.is_running = True
            logger.info(f"Started arbitrage on {len(self.active_chains)} chains")
            return True
        
        except Exception as e:
            logger.error(f"Error starting arbitrage manager: {e}")
            return False
    
    async def stop(self) -> bool:
        """Stop arbitrage on all active chains"""
        if not self.is_running:
            logger.warning("Arbitrage manager is not running")
            return True
        
        try:
            for chain_id in self.active_chains:
                # Stop arbitrage pipeline
                if chain_id in self.arbitrage_pipelines:
                    await self.arbitrage_pipelines[chain_id].stop()
                
                # Stop mempool monitor if available
                if chain_id in self.mempool_monitors:
                    await self.mempool_monitors[chain_id].stop_monitoring()
                
                # Stop token discovery service
                if chain_id in self.token_discovery_services:
                    await self.token_discovery_services[chain_id].stop()
            
            self.is_running = False
            logger.info(f"Stopped arbitrage on {len(self.active_chains)} chains")
            return True
        
        except Exception as e:
            logger.error(f"Error stopping arbitrage manager: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get statistics from all active chains"""
        stats = {
            "global": {
                "active_chains": len(self.active_chains),
                "total_opportunities": 0,
                "total_executions": 0,
                "total_profit": 0.0,
                "total_gas_spent": 0.0,
                "net_profit": 0.0,
            },
            "chains": {}
        }
        
        for chain_id in self.active_chains:
            if chain_id in self.arbitrage_pipelines:
                chain_stats = await self.arbitrage_pipelines[chain_id].get_stats()
                stats["chains"][chain_id] = chain_stats
                
                # Update global stats
                stats["global"]["total_opportunities"] += chain_stats.get("total_opportunities", 0)
                stats["global"]["total_executions"] += chain_stats.get("total_executions", 0)
                stats["global"]["total_profit"] += chain_stats.get("total_profit", 0.0)
                stats["global"]["total_gas_spent"] += chain_stats.get("total_gas_spent", 0.0)
                stats["global"]["net_profit"] += chain_stats.get("net_profit", 0.0)
        
        self.stats = stats
        return stats
    
    async def add_chain(self, chain_id: str, chain_config: Dict[str, Any]) -> bool:
        """Add a new chain to the manager"""
        if chain_id in self.chains:
            logger.warning(f"Chain {chain_id} is already added")
            return False
        
        self.chains.append(chain_id)
        self.config[chain_id] = chain_config
        
        # Initialize the new chain
        was_running = self.is_running
        if was_running:
            await self.stop()
        
        result = await self.initialize()
        
        if was_running and result:
            await self.start()
        
        return result
    
    async def remove_chain(self, chain_id: str) -> bool:
        """Remove a chain from the manager"""
        if chain_id not in self.chains:
            logger.warning(f"Chain {chain_id} is not added")
            return False
        
        was_running = self.is_running
        if was_running:
            await self.stop()
        
        # Remove chain from all collections
        self.chains.remove(chain_id)
        self.active_chains.discard(chain_id)
        
        if chain_id in self.engines:
            del self.engines[chain_id]
        
        if chain_id in self.cross_arbitrage_strategies:
            del self.cross_arbitrage_strategies[chain_id]
        
        if chain_id in self.triangular_arbitrage_strategies:
            del self.triangular_arbitrage_strategies[chain_id]
        
        if chain_id in self.mempool_monitors:
            del self.mempool_monitors[chain_id]
        
        if chain_id in self.flashloan_engines:
            del self.flashloan_engines[chain_id]
        
        if chain_id in self.contract_executors:
            del self.contract_executors[chain_id]
        
        if chain_id in self.token_discovery_services:
            del self.token_discovery_services[chain_id]
        
        if chain_id in self.arbitrage_pipelines:
            del self.arbitrage_pipelines[chain_id]
        
        if chain_id in self.config:
            del self.config[chain_id]
        
        if was_running:
            await self.start()
        
        return True
    
    async def update_chain_config(self, chain_id: str, chain_config: Dict[str, Any]) -> bool:
        """Update configuration for a chain"""
        if chain_id not in self.chains:
            logger.warning(f"Chain {chain_id} is not added")
            return False
        
        # Update config
        self.config[chain_id] = chain_config
        
        # Reinitialize the chain
        was_running = self.is_running
        if was_running:
            await self.stop()
        
        result = await self.initialize()
        
        if was_running and result:
            await self.start()
        
        return result
    
    def get_supported_chains(self) -> List[str]:
        """Get list of supported chains"""
        return list(ChainFactory.SUPPORTED_CHAINS.keys())
    
    def get_active_chains(self) -> List[str]:
        """Get list of active chains"""
        return list(self.active_chains)
    
    async def get_chain_status(self, chain_id: str) -> Dict[str, Any]:
        """Get status of a specific chain"""
        if chain_id not in self.chains:
            return {"error": f"Chain {chain_id} is not added"}
        
        status = {
            "chain_id": chain_id,
            "active": chain_id in self.active_chains,
            "components": {
                "engine": chain_id in self.engines,
                "cross_arbitrage": chain_id in self.cross_arbitrage_strategies,
                "triangular_arbitrage": chain_id in self.triangular_arbitrage_strategies,
                "mempool_monitor": chain_id in self.mempool_monitors,
                "flashloan_engine": chain_id in self.flashloan_engines,
                "contract_executor": chain_id in self.contract_executors,
                "token_discovery": chain_id in self.token_discovery_services,
                "arbitrage_pipeline": chain_id in self.arbitrage_pipelines,
            }
        }
        
        # Get chain-specific stats if available
        if self.stats and "chains" in self.stats and chain_id in self.stats["chains"]:
            status["stats"] = self.stats["chains"][chain_id]
        
        return status