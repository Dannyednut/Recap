import asyncio
import logging
from typing import Dict, List, Any, Optional, Callable
from decimal import Decimal
import time
import json

# Import shared models
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from dex.shared.models.arbitrage_models import ArbitrageOpportunity, ExecutionResult
from dex.shared.utils import decide_execution_mode

# Import local modules
from .config import BSCConfig
from .engine import BSCEngine
from .cross_arbitrage import BSCCrossArbitrageEngine
from .triangular_arbitrage import BSCTriangularArbitrageEngine
from .flashloan_engine import BSCFlashLoanEngine
from .contract_executor import BSCContractExecutor
from .token_discovery import BSCTokenDiscoveryService

logger = logging.getLogger(__name__)

class BSCArbitragePipeline:
    """Unified execution pipeline for all BSC arbitrage strategies"""
    
    def __init__(self, 
                 config: BSCConfig,
                 engine: BSCEngine,
                 cross_arbitrage: BSCCrossArbitrageEngine,
                 triangular_arbitrage: BSCTriangularArbitrageEngine,
                 flashloan_engine: BSCFlashLoanEngine,
                 contract_executor: BSCContractExecutor,
                 token_discovery: BSCTokenDiscoveryService):
        
        self.config = config
        self.engine = engine
        self.cross_arbitrage = cross_arbitrage
        self.triangular_arbitrage = triangular_arbitrage
        self.flashloan_engine = flashloan_engine
        self.contract_executor = contract_executor
        self.token_discovery = token_discovery
        
        # Execution settings
        self.min_profit_threshold = Decimal(str(config.MIN_PROFIT_THRESHOLD))
        self.max_trade_size = Decimal(str(config.MAX_TRADE_SIZE_BNB))
        self.slippage_tolerance = Decimal(str(config.SLIPPAGE_TOLERANCE))
        
        # Opportunity queues
        self.cross_opportunities = asyncio.Queue()
        self.triangular_opportunities = asyncio.Queue()
        
        # Execution stats
        self.execution_stats = {
            "cross": {"attempts": 0, "successes": 0, "failures": 0, "profit": Decimal("0")},
            "triangular": {"attempts": 0, "successes": 0, "failures": 0, "profit": Decimal("0")}
        }
        
        # Callbacks
        self.opportunity_callbacks = []
        self.execution_callbacks = []
        
        # Telegram notifier for trade results
        self.telegram_notifier = None
        
    def set_telegram_notifier(self, notifier):
        """Set the Telegram notifier for trade results"""
        self.telegram_notifier = notifier
        
    async def initialize(self):
        """Initialize the arbitrage pipeline"""
        logger.info("Initializing BSC arbitrage pipeline...")
        
    async def start(self):
        """Start the arbitrage pipeline"""
        logger.info("Starting BSC arbitrage pipeline...")
        
        # Start opportunity processors
        cross_processor = asyncio.create_task(self._process_cross_opportunities())
        triangular_processor = asyncio.create_task(self._process_triangular_opportunities())
        
        # Start opportunity scanners
        cross_scanner = asyncio.create_task(self._scan_cross_opportunities())
        triangular_scanner = asyncio.create_task(self._scan_triangular_opportunities())
        
        # Return all tasks
        return [cross_processor, triangular_processor, cross_scanner, triangular_scanner]
    
    async def stop(self):
        """Stop the arbitrage pipeline"""
        logger.info("Stopping BSC arbitrage pipeline...")
        # Implementation for graceful shutdown
        
    def add_opportunity_callback(self, callback: Callable):
        """Add callback for when opportunities are found"""
        self.opportunity_callbacks.append(callback)
        
    def add_execution_callback(self, callback: Callable):
        """Add callback for when executions complete"""
        self.execution_callbacks.append(callback)
    
    async def _scan_cross_opportunities(self):
        """Continuously scan for cross-exchange arbitrage opportunities"""
        while True:
            try:
                # Get active pairs from token discovery
                active_pairs = await self.token_discovery.get_active_pairs()
                
                # Scan for opportunities
                opportunities = await self.cross_arbitrage.scan_opportunities()
                
                # Filter and queue profitable opportunities
                for opportunity in opportunities:
                    profit = await self.cross_arbitrage.calculate_profit(opportunity)
                    
                    if profit > self.min_profit_threshold:
                        opportunity.estimated_profit = float(profit)
                        await self.cross_opportunities.put(opportunity)
                        
                        # Notify callbacks
                        for callback in self.opportunity_callbacks:
                            await callback(opportunity)
                
                # Sleep before next scan
                await asyncio.sleep(2)  # 2 seconds between scans for BSC
                
            except Exception as e:
                logger.error(f"Error scanning BSC cross opportunities: {e}")
                await asyncio.sleep(5)  # Wait before retry
    
    async def _scan_triangular_opportunities(self):
        """Continuously scan for triangular arbitrage opportunities"""
        while True:
            try:
                # Scan for opportunities
                opportunities = await self.triangular_arbitrage.scan_opportunities()
                
                # Filter and queue profitable opportunities
                for opportunity in opportunities:
                    profit = await self.triangular_arbitrage.calculate_profit(opportunity)
                    
                    if profit > self.min_profit_threshold:
                        opportunity.estimated_profit = float(profit)
                        await self.triangular_opportunities.put(opportunity)
                        
                        # Notify callbacks
                        for callback in self.opportunity_callbacks:
                            await callback(opportunity)
                
                # Sleep before next scan
                await asyncio.sleep(2)  # 2 seconds between scans for BSC
                
            except Exception as e:
                logger.error(f"Error scanning BSC triangular opportunities: {e}")
                await asyncio.sleep(5)  # Wait before retry
    
    async def _process_cross_opportunities(self):
        """Process cross-exchange arbitrage opportunities"""
        while True:
            try:
                # Get opportunity from queue
                opportunity = await self.cross_opportunities.get()
                
                # Check if opportunity is still valid
                profit = await self.cross_arbitrage.calculate_profit(opportunity)
                if profit < self.min_profit_threshold:
                    logger.info(f"BSC Cross opportunity {opportunity.opportunity_id} no longer profitable")
                    continue
                
                # Execute the opportunity
                self.execution_stats["cross"]["attempts"] += 1
                mode = decide_execution_mode(self, opportunity)
                if mode == 'contract_executor':
                    result = await self._execute_cross_arbitrage(opportunity)
                elif mode == 'flashloan_engine':
                    # Use flashloan engine when explicitly requested; normalize its ExecutionResult
                    exec_res = await self.flashloan_engine.execute_opportunity(opportunity)
                    result = self._normalize_execution_result_dict(exec_res)
                else:
                    # Standard strategy path; normalize ExecutionResult to dict used by pipeline
                    exec_res = await self.cross_arbitrage.execute_opportunity(opportunity)
                    result = self._normalize_execution_result_dict(exec_res)
                
                # Update stats
                if result["status"] == "success":
                    self.execution_stats["cross"]["successes"] += 1
                    self.execution_stats["cross"]["profit"] += Decimal(str(result["profit_realized"]))
                else:
                    self.execution_stats["cross"]["failures"] += 1
                
                # Notify callbacks
                for callback in self.execution_callbacks:
                    await callback(opportunity, result)
                
                # Send Telegram notification for completed trade
                if self.telegram_notifier:
                    execution_result = self._convert_to_execution_result(opportunity, result)
                    await self.telegram_notifier.send_trade_result(opportunity, execution_result)
                    
            except Exception as e:
                logger.error(f"Error processing BSC cross opportunity: {e}")
                await asyncio.sleep(1)  # Wait before next opportunity
    
    async def _process_triangular_opportunities(self):
        """Process triangular arbitrage opportunities"""
        while True:
            try:
                # Get opportunity from queue
                opportunity = await self.triangular_opportunities.get()
                
                # Check if opportunity is still valid
                profit = await self.triangular_arbitrage.calculate_profit(opportunity)
                if profit < self.min_profit_threshold:
                    logger.info(f"BSC Triangular opportunity {opportunity.opportunity_id} no longer profitable")
                    continue
                
                # Execute the opportunity
                self.execution_stats["triangular"]["attempts"] += 1
                mode = decide_execution_mode(self, opportunity)
                if mode == 'contract_executor':
                    result = await self._execute_triangular_arbitrage(opportunity)
                elif mode == 'flashloan_engine':
                    exec_res = await self.flashloan_engine.execute_opportunity(opportunity)
                    result = self._normalize_execution_result_dict(exec_res)
                else:
                    exec_res = await self.triangular_arbitrage.execute_opportunity(opportunity)
                    result = self._normalize_execution_result_dict(exec_res)
                
                # Update stats
                if result["status"] == "success":
                    self.execution_stats["triangular"]["successes"] += 1
                    self.execution_stats["triangular"]["profit"] += Decimal(str(result["profit_realized"]))
                else:
                    self.execution_stats["triangular"]["failures"] += 1
                
                # Notify callbacks
                for callback in self.execution_callbacks:
                    await callback(opportunity, result)
                
                # Send Telegram notification for completed trade
                if self.telegram_notifier:
                    execution_result = self._convert_to_execution_result(opportunity, result)
                    await self.telegram_notifier.send_trade_result(opportunity, execution_result)
                    
            except Exception as e:
                logger.error(f"Error processing BSC triangular opportunity: {e}")
                await asyncio.sleep(1)  # Wait before next opportunity
    
    async def _execute_cross_arbitrage(self, opportunity: ArbitrageOpportunity) -> Dict[str, Any]:
        """Execute cross-exchange arbitrage opportunity"""
        try:
            logger.info(f"Executing BSC cross arbitrage: {opportunity.opportunity_id}")
            
            # Prepare contract parameters
            params = {
                "tokenA": opportunity.tokens_path[0].address,
                "tokenB": opportunity.tokens_path[1].address,
                "amountIn": self.engine.w3.to_wei(self.max_trade_size, 'ether'),
                "buyRouter": opportunity.dex_path[0].router_address,
                "sellRouter": opportunity.dex_path[1].router_address,
                "useFlashLoan": True,
                "flashLoanProvider": self.config.VENUS_COMPTROLLER,  # BSC equivalent
                "minProfit": self.engine.w3.to_wei(float(self.min_profit_threshold) / 100 * float(self.max_trade_size), 'ether')
            }
            
            # Execute via contract
            tx_hash = await self.contract_executor.execute_arbitrage(params)
            
            # Wait for transaction receipt
            receipt = await self.engine.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            # Parse events to get profit
            profit = await self.contract_executor.get_profit_from_receipt(receipt)
            
            return {
                "status": "success" if receipt.status == 1 else "failed",
                "tx_hash": tx_hash.hex(),
                "profit_realized": self.engine.w3.from_wei(profit, 'ether'),
                "gas_used": receipt.gasUsed
            }
            
        except Exception as e:
            logger.error(f"Error executing BSC cross arbitrage: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def _execute_triangular_arbitrage(self, opportunity: ArbitrageOpportunity) -> Dict[str, Any]:
        """Execute triangular arbitrage opportunity"""
        try:
            logger.info(f"Executing BSC triangular arbitrage: {opportunity.opportunity_id}")
            
            # Prepare contract parameters
            params = {
                "path": [token.address for token in opportunity.tokens_path],
                "routers": [dex.router_address for dex in opportunity.dex_path],
                "amountIn": self.engine.w3.to_wei(self.max_trade_size, 'ether'),
                "minProfitAmount": self.engine.w3.to_wei(float(self.min_profit_threshold) / 100 * float(self.max_trade_size), 'ether'),
                "flashLoanProvider": 1  # 0 = none, 1 = Venus, 2 = Other
            }
            
            # Execute via contract
            tx_hash = await self.contract_executor.execute_triangular_arbitrage(params)
            
            # Wait for transaction receipt
            receipt = await self.engine.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            # Parse events to get profit
            profit = await self.contract_executor.get_profit_from_receipt(receipt)
            
            return {
                "status": "success" if receipt.status == 1 else "failed",
                "tx_hash": tx_hash.hex(),
                "profit_realized": self.engine.w3.from_wei(profit, 'ether'),
                "gas_used": receipt.gasUsed
            }
            
        except Exception as e:
            logger.error(f"Error executing BSC triangular arbitrage: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }
    
    def _convert_to_execution_result(self, opportunity: ArbitrageOpportunity, result: Dict[str, Any]) -> ExecutionResult:
        """Convert execution result dictionary to ExecutionResult model for Telegram notification"""
        from datetime import datetime
        
        success = result.get("status") == "success"
        
        execution_result = ExecutionResult(
            success=success,
            timestamp=datetime.utcnow(),
            transaction_hash=result.get("tx_hash"),
            gas_cost=result.get("gas_used", 0) * 0.000000005,  # BSC gas cost estimate in USD
            error_message=result.get("error") if not success else None
        )
        
        # Add profit information if successful
        if success and "profit_realized" in result:
            # Rough BNB to USD conversion (should use real price feed in production)
            bnb_price_usd = 300  # Placeholder - should get from price oracle
            execution_result.profit_usd = float(result["profit_realized"]) * bnb_price_usd
        
        return execution_result

    def _normalize_execution_result_dict(self, exec_res: ExecutionResult) -> Dict[str, Any]:
        """Normalize an ExecutionResult into the dict schema used by pipeline internals."""
        try:
            if not exec_res:
                return {"status": "failed", "error": "No result"}
            status = "success" if getattr(exec_res, 'success', False) else "failed"
            tx_hashes = getattr(exec_res, 'transaction_hashes', None)
            tx_hash = tx_hashes[0] if isinstance(tx_hashes, list) and tx_hashes else getattr(exec_res, 'transaction_hash', None)
            profit_usd = getattr(exec_res, 'profit_usd', 0)
            gas_cost_usd = getattr(exec_res, 'gas_cost_usd', 0)
            error = getattr(exec_res, 'error', None) or getattr(exec_res, 'error_message', None)
            return {
                "status": status,
                "tx_hash": tx_hash,
                "profit_realized": Decimal(str(profit_usd)) if profit_usd is not None else Decimal("0"),
                "gas_used": 0,  # not always available; could be estimated elsewhere
                "error": error
            }
        except Exception as e:
            logger.error(f"Error normalizing ExecutionResult: {e}")
            return {"status": "failed", "error": str(e)}

    def get_stats(self) -> Dict[str, Any]:
        """Get execution statistics"""
        return {
            "cross": {
                "attempts": self.execution_stats["cross"]["attempts"],
                "successes": self.execution_stats["cross"]["successes"],
                "failures": self.execution_stats["cross"]["failures"],
                "profit": float(self.execution_stats["cross"]["profit"])
            },
            "triangular": {
                "attempts": self.execution_stats["triangular"]["attempts"],
                "successes": self.execution_stats["triangular"]["successes"],
                "failures": self.execution_stats["triangular"]["failures"],
                "profit": float(self.execution_stats["triangular"]["profit"])
            },
            "total_profit": float(self.execution_stats["cross"]["profit"] + 
                                self.execution_stats["triangular"]["profit"])
        }

# Alias for compatibility
ArbitragePipeline = BSCArbitragePipeline
