import aiohttp
import asyncio
import traceback
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional

from .config import Config
from .cross import CrossExchange
from .triangular import Triangular
from .engine import logger, Engine
from .models import TradeResult
from telegram_alert import TelegramNotifier
from shared_telegram_manager import telegram_manager

# --- Main Application Class ---
class ArbitrageApp:
    def __init__(self, config: Config, config_path: str = 'cex_config.json'):
        self.config = config
        self.config_path = config_path
        self.headers = {
            'api_key': self.config.BASE44_APP_TOKEN,
            'Content-Type': 'application/json'
        }
        
        # State management flags
        self.is_initialized = False
        self.is_running = False
        self.stats_task = None
        
        # Use shared telegram manager instead of individual notifier
        self.telegram_manager = telegram_manager
        
        # Component references (initialized later)
        self.notifier = None
        self.engine = None
        self.cross_engine = None
        self.triangular_engine = None
        self.trade_lock = asyncio.Lock()
        
        # Statistics tracking
        self.stats = {
            'opportunities_detected': 0,
            'trades_executed': 0,
            'successful_trades': 0,
            'failed_trades': 0,
            'total_profit_usd': 0.0,
            'uptime_start': None
        }

    async def initialize(self) -> bool:
        """Initialize the CEX arbitrage app components"""
        if self.is_initialized:
            logger.warning("CEX Arbitrage App is already initialized")
            return True
            
        try:
            logger.info("Initializing CEX Arbitrage App...")
            
            # Initialize Telegram notifier
            if self.config.TELEGRAM_ALERTS_ENABLED and self.config.TELEGRAM_BOT_TOKEN and self.config.TELEGRAM_CHAT_ID:
                try:
                    self.notifier = TelegramNotifier(self.config.TELEGRAM_CHAT_ID)
                    logger.info("Telegram notifier initialized successfully")
                except Exception as e:
                    logger.warning(f"Failed to initialize Telegram notifier: {e}")
                    self.notifier = None
            
            # Initialize engine
            self.engine = Engine(self.config.BASE44_API_URL, self.config.BASE44_APP_TOKEN, self.notifier)
            
            # Initialize exchanges
            await self.engine.initialize_exchanges()
            
            # Initialize arbitrage engines
            self.cross_engine = CrossExchange(self.engine, self.config)
            self.triangular_engine = Triangular(self.engine)
            
            # Initialize stats
            self.stats['uptime_start'] = datetime.utcnow()
            
            self.is_initialized = True
            logger.info("CEX Arbitrage App initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing CEX Arbitrage App: {e}")
            return False

    async def start(self) -> bool:
        """Start the CEX arbitrage app"""
        if not self.is_initialized:
            logger.error("CEX Arbitrage App is not initialized")
            return False
            
        if self.is_running:
            logger.warning("CEX Arbitrage App is already running")
            return True
            
        try:
            logger.info("Starting CEX Arbitrage App scanners...")
            
            # Start all arbitrage scanners
            scanner_tasks = [
                asyncio.create_task(self.cross_engine.start_price_streams()),
                asyncio.create_task(self.triangular_engine.start()),
                asyncio.create_task(self.engine.watch_base44_config()),
                asyncio.create_task(self.engine.update_account_balances_periodically())
            ]
            
            # Start stats reporter
            stats_interval = getattr(self.config, 'STATS_INTERVAL', 60)
            self.stats_task = asyncio.create_task(self._stats_reporter(stats_interval))
            
            # Store tasks for later cleanup
            self.scanner_tasks = scanner_tasks
            
            self.is_running = True
            logger.info("CEX Arbitrage App started successfully")
            
            # Run scanners (this will block until stopped)
            await asyncio.gather(*scanner_tasks)
            return True
            
        except Exception as e:
            logger.error(f"Error starting CEX Arbitrage App: {e}")
            return False

    async def stop(self) -> bool:
        """Stop the CEX arbitrage app"""
        if not self.is_running:
            logger.warning("CEX Arbitrage App is not running")
            return True
            
        try:
            logger.info("Stopping CEX Arbitrage App...")
            
            # Stop engine
            if self.engine:
                await self.engine.stop()
            
            # Cancel stats reporter task
            if self.stats_task:
                self.stats_task.cancel()
                try:
                    await self.stats_task
                except asyncio.CancelledError:
                    pass
                self.stats_task = None
            
            self.is_running = False
            logger.info("CEX Arbitrage App stopped successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping CEX Arbitrage App: {e}")
            return False

    async def run_scanners(self):
        """Legacy method for backward compatibility"""
        logger.warning("run_scanners() is deprecated. Use initialize() then start() instead.")
        if not await self.initialize():
            return
        await self.start()

    async def startup(self):
        """Legacy startup method"""
        return await self.initialize()

    async def shutdown(self):
        """Legacy shutdown method"""
        return await self.stop()

    async def execute_trade_logic(self, trade_request: dict, auth_key: str = None) -> TradeResult:
        """
        Central execution entrypoint. Caller should hold external authentication.
        The orchestrator ensures single concurrent execution through a lock here.
        """
        async with self.trade_lock:
            # Required auth check (API key)
            if not auth_key or auth_key != self.config.BASE44_APP_TOKEN:
                return TradeResult("error", "Unauthorized request - valid API key required")

            op_type = trade_request.get('type')
            entity_name = 'ArbitrageOpportunity' if op_type == 'cross' else 'TriangularOpportunity'

            try:
                # Fetch the latest opportunity record from Base44 (short timeout)
                async with aiohttp.ClientSession() as session:
                    url = f"{self.config.BASE44_API_URL}/entities/{entity_name}/{trade_request.get('opportunity_id')}"
                    async with session.get(url, headers=self.headers, timeout=6) as resp:
                        if resp.status != 200:
                            return TradeResult("error", f"Opportunity not found or expired. Status: {resp.status}")
                        op = await resp.json()

                # Basic staleness check
                try:
                    detected = op.get('detected_at')
                    if detected:
                        age = (datetime.utcnow() - datetime.fromisoformat(detected)).total_seconds()
                        if age > 10:
                            return TradeResult("error", "Opportunity is stale.")
                except Exception:
                    pass

                if op_type == 'cross':
                    return await self.cross_engine._execute_cross_exchange_trade(op, trade_request)
                elif op_type == 'triangular':
                    return await self.triangular_engine._execute_triangular_trade(op, trade_request)

                return TradeResult("error", "Invalid trade type")
            except Exception as e:
                logger.error(f"FATAL error during trade execution pipeline: {e}")
                logger.error(traceback.format_exc())
                return TradeResult("error", "An unexpected server error occurred during execution.")

    async def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status of the CEX arbitrage system"""
        status = {
            "initialized": self.is_initialized,
            "running": self.is_running,
            "exchanges": {},
            "stats": self.stats.copy(),
            "opportunities": {
                "cross_exchange": 0,
                "triangular": 0
            },
            "balances": {}
        }
        
        if self.engine:
            # Get exchange statuses
            for exchange_name, exchange in self.engine.exchanges.items():
                try:
                    status["exchanges"][exchange_name] = {
                        "connected": hasattr(exchange, 'id'),
                        "markets_loaded": len(getattr(exchange, 'markets', {})) > 0,
                        "last_updated": datetime.utcnow().isoformat()
                    }
                except Exception as e:
                    status["exchanges"][exchange_name] = {
                        "connected": False,
                        "error": str(e)
                    }
            
            # Get account balances
            status["balances"] = self.engine.account_balances.copy()
            
            # Calculate uptime
            if self.stats.get('uptime_start'):
                uptime_seconds = (datetime.utcnow() - self.stats['uptime_start']).total_seconds()
                status["stats"]["uptime_seconds"] = uptime_seconds
        
        return status

    async def get_opportunities(self) -> Dict[str, Any]:
        """Get current arbitrage opportunities"""
        opportunities = {
            "cross_exchange": [],
            "triangular": [],
            "total_count": 0
        }
        
        if not self.is_running or not self.engine:
            return opportunities
        
        try:
            # This would need to be implemented in the engines to track current opportunities
            # For now, return empty structure
            pass
        except Exception as e:
            logger.error(f"Error getting opportunities: {e}")
        
        return opportunities

    async def update_stats(self, stat_type: str, value: Any = 1):
        """Update statistics"""
        if stat_type in self.stats:
            if isinstance(self.stats[stat_type], (int, float)):
                self.stats[stat_type] += value
            else:
                self.stats[stat_type] = value

    async def _stats_reporter(self, interval: int = 60):
        """Report statistics periodically"""
        while True:
            try:
                if self.is_running:
                    # Log current stats
                    logger.info(f"CEX Arbitrage Stats: {json.dumps(self.stats, indent=2, default=str)}")
                    
                    # Save stats to file
                    stats_file = 'cex_stats.json'
                    with open(stats_file, 'w') as f:
                        json.dump(self.stats, f, indent=2, default=str)
                
                await asyncio.sleep(interval)
            
            except asyncio.CancelledError:
                break
            
            except Exception as e:
                logger.error(f"Error in CEX stats reporter: {e}")
                await asyncio.sleep(interval)

    async def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        try:
            if not os.path.exists(self.config_path):
                logger.warning(f"Config file {self.config_path} not found, using default config")
                return self._create_default_config()
            
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            logger.info(f"Loaded CEX configuration from {self.config_path}")
            return config
        
        except Exception as e:
            logger.error(f"Error loading CEX config: {e}")
            return self._create_default_config()

    async def _save_config(self, config_data: Dict[str, Any]) -> bool:
        """Save configuration to file"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            logger.info(f"Saved CEX configuration to {self.config_path}")
            return True
        
        except Exception as e:
            logger.error(f"Error saving CEX config: {e}")
            return False

    def _create_default_config(self) -> Dict[str, Any]:
        """Create default configuration"""
        return {
            "base44": {
                "api_url": "https://api.base44.com",
                "app_token": "",
                "execute_url": "http://localhost:5000/execute"
            },
            "telegram": {
                "alerts_enabled": True,
                "bot_token": "",
                "chat_id": ""
            },
            "trading": {
                "min_profit_threshold": 0.3,
                "max_trade_amount": 1000,
                "symbols": ["BTC/USDT", "ETH/USDT", "BNB/USDT"],
                "reconnect_delay": 30
            },
            "flask": {
                "host": "0.0.0.0",
                "port": 5000
            },
            "global": {
                "stats_interval": 60,
                "log_level": "INFO"
            }
        }

    async def update_config(self, new_config: Dict[str, Any]) -> bool:
        """Update configuration dynamically"""
        try:
            # Save new config
            if await self._save_config(new_config):
                logger.info("Configuration updated successfully")
                return True
            return False
        
        except Exception as e:
            logger.error(f"Error updating config: {e}")
            return False
