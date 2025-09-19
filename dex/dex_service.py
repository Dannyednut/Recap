import asyncio
import logging
import json
import os
from typing import Dict, Any, List, Optional

from .arbitrage_manager import ArbitrageManager
from .orchestrator.main import DEXArbitrageOrchestrator
from .shared.orchestration_config import (
    get_orchestration_config, 
    determine_optimal_mode, 
    get_chain_capabilities,
    OrchestrationMode,
    validate_config
)
from .shared.network_config import NetworkConfig

logger = logging.getLogger(__name__)

class MultiChainDEXService:
    """Service for managing multi-chain DEX arbitrage with configurable orchestration layers"""
    
    def __init__(self, config_path: str = 'dex_config.json'):
        """Initialize the DEX service"""
        self.config_path = config_path
        self.config = {}
        self.orchestration_config = get_orchestration_config()
        self.orchestration_mode = None
        
        # Orchestration layer instances
        self.manager = None  # ArbitrageManager (simple layer)
        self.orchestrator = None  # DEXArbitrageOrchestrator (advanced layer)
        
        self.is_initialized = False
        self.is_running = False
        self.stats_task = None
    
    async def initialize(self) -> bool:
        """Initialize the DEX service with appropriate orchestration layer"""
        try:
            # Load configuration
            self.config = await self._load_config()
            
            # Validate orchestration configuration
            validation = validate_config(self.orchestration_config)
            if not validation['valid']:
                logger.error(f"Orchestration config validation failed: {validation['issues']}")
                return False
            
            if validation['recommendations']:
                for rec in validation['recommendations']:
                    logger.warning(f"Orchestration recommendation: {rec}")
            
            # Determine optimal orchestration mode with chain capability awareness
            chains = self.config.get('chains', ['ethereum'])
            chain_count = len(chains)
            chain_capabilities = get_chain_capabilities(chains)
            self.orchestration_mode = determine_optimal_mode(self.orchestration_config, chain_count, chain_capabilities)
            
            logger.info(f"Using orchestration mode: {self.orchestration_mode.value}")
            logger.info(f"Mode description: {validation['mode_description']}")
            
            # Initialize appropriate orchestration layer
            if self.orchestration_mode == OrchestrationMode.SIMPLE:
                return await self._initialize_simple_layer()
            else:
                return await self._initialize_advanced_layer()
        
        except Exception as e:
            logger.error(f"Error initializing DEX service: {e}")
            return False
    
    async def start(self) -> bool:
        """Start the DEX service"""
        if not self.is_initialized:
            logger.error("DEX service is not initialized")
            return False
        
        if self.is_running:
            logger.warning("DEX service is already running")
            return True
        
        try:
            # Start appropriate orchestration layer
            if self.orchestration_mode == OrchestrationMode.SIMPLE:
                success = await self._start_simple_layer()
            else:
                success = await self._start_advanced_layer()
            
            if not success:
                return False
            
            # Start stats reporter
            stats_interval = self.config.get('global', {}).get('stats_interval', 60)
            self.stats_task = asyncio.create_task(self._stats_reporter(stats_interval))
            
            self.is_running = True
            logger.info(f"DEX service started successfully using {self.orchestration_mode.value} layer")
            return True
        
        except Exception as e:
            logger.error(f"Error starting DEX service: {e}")
            return False
    
    async def stop(self) -> bool:
        """Stop the DEX service"""
        if not self.is_running:
            logger.warning("DEX service is not running")
            return True
        
        try:
            # Stop appropriate orchestration layer
            if self.orchestration_mode == OrchestrationMode.SIMPLE:
                await self._stop_simple_layer()
            else:
                await self._stop_advanced_layer()
            
            # Cancel stats reporter task
            if self.stats_task:
                self.stats_task.cancel()
                try:
                    await self.stats_task
                except asyncio.CancelledError:
                    pass
                self.stats_task = None
            
            self.is_running = False
            logger.info(f"DEX service stopped successfully ({self.orchestration_mode.value} layer)")
            return True
        
        except Exception as e:
            logger.error(f"Error stopping DEX service: {e}")
            return False
    
    async def get_status(self) -> Dict[str, Any]:
        """Get status of the DEX service"""
        status = {
            "initialized": self.is_initialized,
            "running": self.is_running,
            "chains": {},
            "stats": {}
        }
        
        if self.manager:
            # Get active chains
            active_chains = self.manager.get_active_chains()
            status["active_chains"] = active_chains
            
            # Get chain statuses
            for chain_id in active_chains:
                chain_status = await self.manager.get_chain_status(chain_id)
                status["chains"][chain_id] = chain_status
            
            # Get stats
            stats = await self.manager.get_stats()
            status["stats"] = stats
        
        return status
    
    async def get_opportunities(self, chain_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get current arbitrage opportunities"""
        opportunities = []
        
        if not self.manager:
            return opportunities
        
        active_chains = self.manager.get_active_chains()
        target_chains = [chain_id] if chain_id and chain_id in active_chains else active_chains
        
        for chain in target_chains:
            if chain in self.manager.arbitrage_pipelines:
                pipeline = self.manager.arbitrage_pipelines[chain]
                chain_opportunities = await pipeline.get_current_opportunities()
                
                # Add chain identifier to each opportunity
                for opp in chain_opportunities:
                    opp["chain_id"] = chain
                
                opportunities.extend(chain_opportunities)
        
        return opportunities
    
    async def execute_opportunity(self, opportunity_id: str, chain_id: str) -> Dict[str, Any]:
        """Execute a specific arbitrage opportunity"""
        if not self.manager or chain_id not in self.manager.arbitrage_pipelines:
            return {"status": "error", "message": f"Chain {chain_id} not available"}
        
        pipeline = self.manager.arbitrage_pipelines[chain_id]
        result = await pipeline.execute_opportunity_by_id(opportunity_id)
        return result
    
    async def add_chain(self, chain_id: str, chain_config: Dict[str, Any]) -> bool:
        """Add a new chain to the service"""
        if not self.manager:
            return False
        
        # Add chain to config
        self.config[chain_id] = chain_config
        if chain_id not in self.config["chains"]:
            self.config["chains"].append(chain_id)
        
        # Save config
        await self._save_config()
        
        # Add chain to manager
        return await self.manager.add_chain(chain_id, chain_config)
    
    async def remove_chain(self, chain_id: str) -> bool:
        """Remove a chain from the service"""
        if not self.manager:
            return False
        
        # Remove chain from config
        if chain_id in self.config:
            del self.config[chain_id]
        
        if chain_id in self.config["chains"]:
            self.config["chains"].remove(chain_id)
        
        # Save config
        await self._save_config()
        
        # Remove chain from manager
        return await self.manager.remove_chain(chain_id)
    
    async def update_chain_config(self, chain_id: str, chain_config: Dict[str, Any]) -> bool:
        """Update configuration for a chain"""
        if not self.manager:
            return False
        
        # Update config
        self.config[chain_id] = chain_config
        
        # Save config
        await self._save_config()
        
        # Update chain in manager
        return await self.manager.update_chain_config(chain_id, chain_config)
    
    async def get_supported_chains(self) -> List[str]:
        """Get list of supported chains"""
        if not self.manager:
            return []
        
        return self.manager.get_supported_chains()
    
    async def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        try:
            if not os.path.exists(self.config_path):
                logger.warning(f"Config file {self.config_path} not found, using default config")
                return self._create_default_config()
            
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            logger.info(f"Loaded configuration from {self.config_path}")
            return config
        
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return self._create_default_config()
    
    async def _save_config(self) -> bool:
        """Save configuration to file"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            
            logger.info(f"Saved configuration to {self.config_path}")
            return True
        
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False
    
    def _create_default_config(self) -> Dict[str, Any]:
        """Create default configuration"""
        config = NetworkConfig.get_all_configs()
        return {
            "chains": [chain for chain in config],
            "ethereum": config["ethereum"],
            "bsc": config["bsc"],
            "polygon": config["polygon"],
            "solana": config["solana"],
            "global": {
                "log_level": "INFO",
                "stats_interval": 60,  # seconds
                "max_concurrent_executions": 1,
                "execution_timeout": 30,  # seconds
                "gas_price_multiplier": 1.1,  # 10% buffer
                "max_slippage": 0.005,  # 0.5%
            }
        }
    
    async def _stats_reporter(self, interval: int = 60):
        """Report statistics periodically"""
        while True:
            try:
                if self.manager:
                    stats = await self.manager.get_stats()
                    logger.info(f"Arbitrage Stats: {json.dumps(stats['global'], indent=2)}")
                    
                
                await asyncio.sleep(interval)
            
            except asyncio.CancelledError:
                break
            
            except Exception as e:
                logger.error(f"Error in stats reporter: {e}")
                await asyncio.sleep(interval)

    
    # =============================================================================
    # ORCHESTRATION LAYER MANAGEMENT
    # =============================================================================

    async def _initialize_simple_layer(self) -> bool:
        """Initialize the simple orchestration layer"""
        try:
            logger.info("Initializing Simple Layer (ArbitrageManager)...")
            self.manager = ArbitrageManager(self.config)
            
            if not await self.manager.initialize():
                logger.error("Failed to initialize arbitrage manager")
                return False
            
            self.is_initialized = True
            logger.info("Simple layer initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Error initializing simple layer: {e}")
            return False

    async def _start_simple_layer(self) -> bool:
        """Start the simple orchestration layer"""
        if not await self.manager.start():
            logger.error("Failed to start arbitrage manager")
            return False
        return True

    async def _stop_simple_layer(self) -> bool:
        """Stop the simple orchestration layer"""
        if self.manager:
            await self.manager.stop()
        return True

    async def _initialize_advanced_layer(self) -> bool:
        """Initialize the advanced orchestration layer"""
        try:
            logger.info("Initializing Advanced Layer (DEXArbitrageOrchestrator)...")
            self.orchestrator = DEXArbitrageOrchestrator()
            
            # Configure orchestrator with our settings
            self.orchestrator.config.update({
                "max_concurrent_executions": self.orchestration_config.max_concurrent_executions,
                "min_profit_threshold_usd": self.orchestration_config.min_profit_threshold_usd,
                "max_position_size_usd": self.orchestration_config.max_position_size_usd,
                "execution_timeout": self.orchestration_config.execution_timeout,
                "health_check_interval": self.orchestration_config.health_check_interval
            })
            
            await self.orchestrator.initialize()
            
            self.is_initialized = True
            logger.info("Advanced layer initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Error initializing advanced layer: {e}")
            return False

    async def _start_advanced_layer(self) -> bool:
        """Start the advanced orchestration layer"""
        # The orchestrator starts automatically during initialization
        return True

    async def _stop_advanced_layer(self) -> bool:
        """Stop the advanced orchestration layer"""
        if self.orchestrator:
            await self.orchestrator.shutdown()
        return True

    async def get_orchestration_status(self) -> Dict[str, Any]:
        """Get detailed orchestration layer status"""
        base_status = {
            "orchestration_mode": self.orchestration_mode.value if self.orchestration_mode else "unknown",
            "layer_description": self.orchestration_config.__dict__ if self.orchestration_config else {},
            "initialized": self.is_initialized,
            "running": self.is_running
        }
        
        if self.orchestration_mode == OrchestrationMode.SIMPLE and self.manager:
            # Get simple layer status
            base_status.update({
                "active_chains": self.manager.get_active_chains(),
                "stats": await self.manager.get_stats() if self.is_running else {}
            })
        elif self.orchestration_mode == OrchestrationMode.ADVANCED and self.orchestrator:
            # Get advanced layer status
            try:
                system_health = await self.orchestrator.get_system_status()
                base_status.update({
                    "system_health": system_health.__dict__,
                    "active_chains": system_health.active_chains,
                    "inactive_chains": system_health.inactive_chains,
                    "total_opportunities": system_health.total_opportunities,
                    "execution_success_rate": system_health.execution_success_rate
                })
            except Exception as e:
                base_status["orchestrator_error"] = str(e)
        
        return base_status

    async def switch_orchestration_mode(self, new_mode: str) -> bool:
        """Switch orchestration mode at runtime"""
        try:
            # Parse new mode
            try:
                target_mode = OrchestrationMode(new_mode.lower())
            except ValueError:
                logger.error(f"Invalid orchestration mode: {new_mode}")
                return False
            
            if target_mode == self.orchestration_mode:
                logger.info(f"Already using {target_mode.value} mode")
                return True
            
            logger.info(f"Switching from {self.orchestration_mode.value} to {target_mode.value} mode")
            
            # Stop current layer
            was_running = self.is_running
            if was_running:
                await self.stop()
            
            # Update mode
            self.orchestration_mode = target_mode
            
            # Initialize new layer
            if target_mode == OrchestrationMode.SIMPLE:
                success = await self._initialize_simple_layer()
            else:
                success = await self._initialize_advanced_layer()
            
            if not success:
                logger.error(f"Failed to initialize {target_mode.value} layer")
                return False
            
            # Restart if it was running
            if was_running:
                await self.start()
            
            logger.info(f"Successfully switched to {target_mode.value} mode")
            return True
            
        except Exception as e:
            logger.error(f"Error switching orchestration mode: {e}")
            return False