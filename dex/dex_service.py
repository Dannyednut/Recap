import asyncio
import logging
import json
import os
from typing import Dict, Any, List, Optional

from .arbitrage_manager import ArbitrageManager

logger = logging.getLogger(__name__)

class MultiChainDEXService:
    """Service for managing multi-chain DEX arbitrage"""
    
    def __init__(self, config_path: str = 'dex_config.json'):
        """Initialize the DEX service"""
        self.config_path = config_path
        self.config = {}
        self.manager = None
        self.is_initialized = False
        self.is_running = False
        self.stats_task = None
    
    async def initialize(self) -> bool:
        """Initialize the DEX service"""
        try:
            # Load configuration
            self.config = await self._load_config()
            
            # Create arbitrage manager
            self.manager = ArbitrageManager(self.config)
            
            # Initialize manager
            if not await self.manager.initialize():
                logger.error("Failed to initialize arbitrage manager")
                return False
            
            self.is_initialized = True
            logger.info("DEX service initialized successfully")
            return True
        
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
            # Start arbitrage manager
            if not await self.manager.start():
                logger.error("Failed to start arbitrage manager")
                return False
            
            # Start stats reporter
            stats_interval = self.config.get('global', {}).get('stats_interval', 60)
            self.stats_task = asyncio.create_task(self._stats_reporter(stats_interval))
            
            self.is_running = True
            logger.info("DEX service started successfully")
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
            # Stop arbitrage manager
            if self.manager:
                await self.manager.stop()
            
            # Cancel stats reporter task
            if self.stats_task:
                self.stats_task.cancel()
                try:
                    await self.stats_task
                except asyncio.CancelledError:
                    pass
                self.stats_task = None
            
            self.is_running = False
            logger.info("DEX service stopped successfully")
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
        return {
            "chains": ["ethereum"],
            "ethereum": {
                "rpc_url": "https://mainnet.infura.io/v3/YOUR_INFURA_KEY",
                "ws_url": "wss://mainnet.infura.io/ws/v3/YOUR_INFURA_KEY",
                "private_key": "",  # Add your private key here
                "min_profit_threshold": 0.001,  # 0.1%
                "use_flashloan_by_default": True,
                "mempool_enabled": True,
                "token_whitelist": [],  # Empty means all tokens
                "token_blacklist": [],  # Tokens to exclude
            },
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
                    
                    # Save stats to file
                    with open('dex_stats.json', 'w') as f:
                        json.dump(stats, f, indent=2)
                
                await asyncio.sleep(interval)
            
            except asyncio.CancelledError:
                break
            
            except Exception as e:
                logger.error(f"Error in stats reporter: {e}")
                await asyncio.sleep(interval)