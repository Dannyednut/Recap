import asyncio
import logging
from typing import Dict, List, Any, Optional
from decimal import Decimal
from datetime import datetime

from .engine import BSCEngine
from .config import BSCConfig
from .cross_arbitrage import BSCCrossArbitrageEngine
from .triangular_arbitrage import BSCTriangularArbitrageEngine
from .flashloan_engine import BSCFlashLoanEngine

# Shared imports
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from models.arbitrage_models import ArbitrageOpportunity, ExecutionResult
from telegram_notifier import DEXTelegramNotifier

logger = logging.getLogger(__name__)

class BSCArbitrageService:
    """Main BSC arbitrage service coordinating all arbitrage engines"""
    
    def __init__(self, config: BSCConfig = None):
        self.config = config or BSCConfig()
        self.chain = "bsc"
        self.chain_id = self.config.CHAIN_ID
        
        # Core engine
        self.engine = BSCEngine(self.config)
        
        # Telegram notifier for trade results
        self.telegram_notifier = DEXTelegramNotifier()
        
        # Arbitrage engines
        self.cross_arbitrage = BSCCrossArbitrageEngine(self.engine, self.config)
        self.triangular_arbitrage = BSCTriangularArbitrageEngine(self.engine, self.config)
        self.flash_loan = BSCFlashLoanEngine(self.engine, self.config)
        
        self.is_initialized = False
        self.last_health_check = datetime.now()
        
    async def initialize(self) -> None:
        """Initialize all components"""
        try:
            logger.info("Initializing BSC Arbitrage Service...")
            
            # Initialize core engine
            await self.engine.initialize()
            
            # Initialize arbitrage engines
            await self.cross_arbitrage.initialize()
            await self.triangular_arbitrage.initialize()
            await self.flash_loan.initialize()
            
            self.is_initialized = True
            logger.info("BSC Arbitrage Service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize BSC Arbitrage Service: {e}")
            raise
    
    async def scan_opportunities(self) -> List[ArbitrageOpportunity]:
        """Scan for all types of arbitrage opportunities"""
        if not self.is_initialized:
            logger.warning("BSC Service not initialized")
            return []
        
        try:
            all_opportunities = []
            
            # Get cross-exchange opportunities
            cross_ops = await self.cross_arbitrage.scan_opportunities()
            all_opportunities.extend(cross_ops)
            
            # Get triangular arbitrage opportunities
            triangular_ops = await self.triangular_arbitrage.scan_opportunities()
            all_opportunities.extend(triangular_ops)
            
            # Get flash loan opportunities
            flash_ops = await self.flash_loan.scan_opportunities()
            all_opportunities.extend(flash_ops)
            
            logger.info(f"Found {len(all_opportunities)} opportunities on BSC")
            return all_opportunities
            
        except Exception as e:
            logger.error(f"Error scanning BSC opportunities: {e}")
            return []
    
    async def execute_opportunity(self, opportunity: ArbitrageOpportunity) -> ExecutionResult:
        """Execute a specific arbitrage opportunity"""
        if not self.is_initialized:
            raise RuntimeError("BSC Service not initialized")
        
        try:
            logger.info(f"Executing BSC opportunity {opportunity.id} of type {opportunity.type}")
            
            if opportunity.type == "cross_exchange":
                result = await self.cross_arbitrage.execute_opportunity(opportunity)
            elif opportunity.type == "triangular":
                result = await self.triangular_arbitrage.execute_opportunity(opportunity)
            elif opportunity.type == "flash_loan":
                result = await self.flash_loan.execute_opportunity(opportunity)
            else:
                raise ValueError(f"Unknown opportunity type: {opportunity.type}")
            
            # Send Telegram notification for completed trade
            if self.telegram_notifier and result:
                await self.telegram_notifier.send_trade_result(opportunity, result)
            
            return result
                
        except Exception as e:
            logger.error(f"Error executing BSC opportunity {opportunity.id}: {e}")
            result = ExecutionResult(
                opportunity_id=opportunity.id,
                success=False,
                profit_usd=Decimal("0"),
                gas_cost_usd=Decimal("0"),
                execution_time=0.0,
                error=str(e)
            )
            
            # Send Telegram notification for failed trade
            if self.telegram_notifier:
                await self.telegram_notifier.send_trade_result(opportunity, result)
            
            return result
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get service health status"""
        try:
            self.last_health_check = datetime.now()
            
            # Check engine health
            engine_health = await self._check_engine_health()
            
            # Check component health
            components_health = await self._check_components_health()
            
            overall_healthy = (
                engine_health["status"] == "healthy" and
                all(comp["status"] == "healthy" for comp in components_health.values())
            )
            
            return {
                "status": "healthy" if overall_healthy else "degraded",
                "timestamp": self.last_health_check.isoformat(),
                "chain": self.chain,
                "chain_id": self.chain_id,
                "engine": engine_health,
                "components": components_health,
                "initialized": self.is_initialized
            }
            
        except Exception as e:
            logger.error(f"BSC Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def _check_engine_health(self) -> Dict[str, Any]:
        """Check core engine health"""
        try:
            if not self.engine or not self.engine.w3:
                return {"status": "unhealthy", "error": "Engine not initialized"}
            
            # Test connection
            is_connected = await self.engine.w3.is_connected()
            if not is_connected:
                return {"status": "unhealthy", "error": "Web3 connection failed"}
            
            # Test wallet
            if self.engine.wallet_address:
                balance = await self.engine.get_balance("0x0")  # BNB balance
                return {
                    "status": "healthy",
                    "wallet_address": self.engine.wallet_address,
                    "bnb_balance": str(balance)
                }
            else:
                return {"status": "degraded", "warning": "No wallet configured"}
                
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def _check_components_health(self) -> Dict[str, Dict[str, Any]]:
        """Check arbitrage components health"""
        components = {
            "cross_arbitrage": self.cross_arbitrage,
            "triangular_arbitrage": self.triangular_arbitrage,
            "flash_loan": self.flash_loan
        }
        
        health_status = {}
        
        for name, component in components.items():
            try:
                if hasattr(component, 'get_health_status'):
                    health_status[name] = await component.get_health_status()
                else:
                    # Basic health check
                    health_status[name] = {
                        "status": "healthy" if hasattr(component, 'initialized') else "unknown",
                        "initialized": getattr(component, 'initialized', False)
                    }
            except Exception as e:
                health_status[name] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
        
        return health_status
    
    async def ping(self) -> bool:
        """Simple ping for heartbeat monitoring"""
        try:
            if not self.is_initialized:
                return False
            
            # Quick Web3 connection test
            if self.engine and self.engine.w3:
                return await self.engine.w3.is_connected()
            
            return False
            
        except Exception:
            return False
    
    async def shutdown(self) -> None:
        """Graceful shutdown"""
        try:
            logger.info("Shutting down BSC Arbitrage Service...")
            
            # Close engine connections
            if self.engine:
                await self.engine.shutdown()
            
            self.is_initialized = False
            logger.info("BSC Arbitrage Service shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during BSC shutdown: {e}")
    
    async def restart(self) -> None:
        """Restart the service"""
        await self.shutdown()
        await self.initialize()
        logger.info("BSC Arbitrage Service restarted")