import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import json

# Shared imports
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from shared.models.arbitrage_models import ArbitrageOpportunity, ExecutionResult

logger = logging.getLogger(__name__)

class ExecutionStatus(Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class ExecutionPlan:
    opportunity_id: str
    execution_type: str  # "cross", "triangular", "flash_loan"
    steps: List[Dict[str, Any]]
    estimated_gas: int
    estimated_time: float
    risk_level: str
    required_balance: Decimal

@dataclass
class ExecutionMetrics:
    total_executions: int
    successful_executions: int
    failed_executions: int
    total_profit_usd: Decimal
    total_gas_cost_usd: Decimal
    average_execution_time: float
    success_rate: float

class ExecutionCoordinator:
    """Coordinates arbitrage opportunity execution across all chains"""
    
    def __init__(self):
        self.active_executions: Dict[str, Dict[str, Any]] = {}
        self.execution_history: List[ExecutionResult] = {}
        self.execution_queue: List[Tuple[ArbitrageOpportunity, ExecutionPlan]] = []
        
        # Configuration
        self.config = {
            "max_concurrent_executions": 3,
            "execution_timeout": 300,  # 5 minutes
            "retry_attempts": 2,
            "min_success_rate": 70.0,  # %
            "gas_price_multiplier": 1.1,
            "slippage_tolerance": 0.5  # %
        }
        
        # Metrics
        self.metrics = ExecutionMetrics(
            total_executions=0,
            successful_executions=0,
            failed_executions=0,
            total_profit_usd=Decimal("0"),
            total_gas_cost_usd=Decimal("0"),
            average_execution_time=0.0,
            success_rate=0.0
        )
    
    async def initialize(self) -> None:
        """Initialize execution coordinator"""
        logger.info("Initializing Execution Coordinator...")
        
        # Start background tasks
        asyncio.create_task(self._execution_monitor())
        asyncio.create_task(self._metrics_updater())
        
        logger.info("Execution Coordinator initialized")
    
    async def execute_opportunity(
        self, 
        service: Any, 
        opportunity: ArbitrageOpportunity
    ) -> ExecutionResult:
        """Execute an arbitrage opportunity using the appropriate service"""
        try:
            execution_id = f"exec_{opportunity.id}_{datetime.now().timestamp()}"
            
            logger.info(f"Starting execution {execution_id} for opportunity {opportunity.id}")
            
            # Create execution plan
            execution_plan = await self._create_execution_plan(opportunity)
            if not execution_plan:
                raise ValueError("Failed to create execution plan")
            
            # Register execution
            self.active_executions[execution_id] = {
                "opportunity": opportunity,
                "plan": execution_plan,
                "service": service,
                "status": ExecutionStatus.PENDING,
                "start_time": datetime.now(),
                "retry_count": 0
            }
            
            # Execute based on opportunity type
            if opportunity.type == "cross_exchange":
                result = await self._execute_cross_exchange(execution_id, service, opportunity, execution_plan)
            elif opportunity.type == "triangular":
                result = await self._execute_triangular(execution_id, service, opportunity, execution_plan)
            elif opportunity.type == "flash_loan":
                result = await self._execute_flash_loan(execution_id, service, opportunity, execution_plan)
            else:
                raise ValueError(f"Unknown opportunity type: {opportunity.type}")
            
            # Update execution status
            self.active_executions[execution_id]["status"] = (
                ExecutionStatus.COMPLETED if result.success else ExecutionStatus.FAILED
            )
            
            # Record result
            self.execution_history.append(result)
            await self._update_metrics(result)
            
            logger.info(f"Execution {execution_id} completed: Success={result.success}, Profit=${result.profit_usd}")
            return result
            
        except Exception as e:
            logger.error(f"Error executing opportunity {opportunity.id}: {e}")
            
            # Mark as failed
            if execution_id in self.active_executions:
                self.active_executions[execution_id]["status"] = ExecutionStatus.FAILED
            
            # Create error result
            error_result = ExecutionResult(
                opportunity_id=opportunity.id,
                success=False,
                profit_usd=Decimal("0"),
                gas_cost_usd=Decimal("0"),
                execution_time=0.0,
                error=str(e)
            )
            
            self.execution_history.append(error_result)
            await self._update_metrics(error_result)
            
            return error_result
        
        finally:
            # Clean up active execution
            if execution_id in self.active_executions:
                del self.active_executions[execution_id]
    
    async def _create_execution_plan(self, opportunity: ArbitrageOpportunity) -> Optional[ExecutionPlan]:
        """Create detailed execution plan for opportunity"""
        try:
            steps = []
            estimated_gas = 0
            
            if opportunity.type == "cross_exchange":
                # Plan for cross-exchange arbitrage
                steps = [
                    {
                        "action": "check_balances",
                        "tokens": [opportunity.token_a, opportunity.token_b]
                    },
                    {
                        "action": "approve_tokens",
                        "token": opportunity.token_a,
                        "spender": opportunity.exchange_a,
                        "amount": opportunity.amount_in
                    },
                    {
                        "action": "swap",
                        "exchange": opportunity.exchange_a,
                        "token_in": opportunity.token_a,
                        "token_out": opportunity.token_b,
                        "amount_in": opportunity.amount_in
                    },
                    {
                        "action": "approve_tokens",
                        "token": opportunity.token_b,
                        "spender": opportunity.exchange_b,
                        "amount": opportunity.amount_out
                    },
                    {
                        "action": "swap",
                        "exchange": opportunity.exchange_b,
                        "token_in": opportunity.token_b,
                        "token_out": opportunity.token_a,
                        "amount_in": opportunity.amount_out
                    }
                ]
                estimated_gas = 400000  # Estimated for 2 swaps + approvals
                
            elif opportunity.type == "triangular":
                # Plan for triangular arbitrage
                steps = [
                    {
                        "action": "check_balances",
                        "tokens": [opportunity.token_a, opportunity.token_b, opportunity.token_c]
                    },
                    {
                        "action": "multi_swap",
                        "path": [opportunity.token_a, opportunity.token_b, opportunity.token_c, opportunity.token_a],
                        "amounts": [opportunity.amount_in, opportunity.amount_ab, opportunity.amount_bc, opportunity.amount_out]
                    }
                ]
                estimated_gas = 500000  # Estimated for triangular swap
                
            elif opportunity.type == "flash_loan":
                # Plan for flash loan arbitrage
                steps = [
                    {
                        "action": "flash_loan",
                        "token": opportunity.token_a,
                        "amount": opportunity.loan_amount,
                        "callback_data": {
                            "swaps": opportunity.swap_sequence,
                            "expected_profit": opportunity.profit_usd
                        }
                    }
                ]
                estimated_gas = 600000  # Estimated for flash loan execution
            
            return ExecutionPlan(
                opportunity_id=opportunity.id,
                execution_type=opportunity.type,
                steps=steps,
                estimated_gas=estimated_gas,
                estimated_time=estimated_gas / 100000,  # Rough time estimate
                risk_level=self._assess_risk_level(opportunity),
                required_balance=opportunity.amount_in if hasattr(opportunity, 'amount_in') else Decimal("0")
            )
            
        except Exception as e:
            logger.error(f"Error creating execution plan: {e}")
            return None
    
    def _assess_risk_level(self, opportunity: ArbitrageOpportunity) -> str:
        """Assess risk level for opportunity"""
        risk_score = getattr(opportunity, 'risk_score', 50)
        
        if risk_score < 30:
            return "low"
        elif risk_score < 60:
            return "medium"
        else:
            return "high"
    
    async def _execute_cross_exchange(
        self,
        execution_id: str,
        service: Any,
        opportunity: ArbitrageOpportunity,
        plan: ExecutionPlan
    ) -> ExecutionResult:
        """Execute cross-exchange arbitrage"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            self.active_executions[execution_id]["status"] = ExecutionStatus.EXECUTING
            
            # Execute through service's cross arbitrage engine
            if hasattr(service, 'cross_arbitrage'):
                result = await service.cross_arbitrage.execute_opportunity(opportunity)
                
                execution_time = asyncio.get_event_loop().time() - start_time
                
                return ExecutionResult(
                    opportunity_id=opportunity.id,
                    success=result.get("success", False),
                    profit_usd=result.get("profit_usd", Decimal("0")),
                    gas_cost_usd=result.get("gas_cost_usd", Decimal("0")),
                    execution_time=execution_time,
                    transaction_hashes=result.get("transaction_hashes", []),
                    error=result.get("error")
                )
            else:
                raise ValueError("Service does not support cross-exchange arbitrage")
                
        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"Cross-exchange execution failed: {e}")
            
            return ExecutionResult(
                opportunity_id=opportunity.id,
                success=False,
                profit_usd=Decimal("0"),
                gas_cost_usd=Decimal("0"),
                execution_time=execution_time,
                error=str(e)
            )
    
    async def _execute_triangular(
        self,
        execution_id: str,
        service: Any,
        opportunity: ArbitrageOpportunity,
        plan: ExecutionPlan
    ) -> ExecutionResult:
        """Execute triangular arbitrage"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            self.active_executions[execution_id]["status"] = ExecutionStatus.EXECUTING
            
            # Execute through service's triangular arbitrage engine
            if hasattr(service, 'triangular_arbitrage'):
                result = await service.triangular_arbitrage.execute_opportunity(opportunity)
                
                execution_time = asyncio.get_event_loop().time() - start_time
                
                return ExecutionResult(
                    opportunity_id=opportunity.id,
                    success=result.get("success", False),
                    profit_usd=result.get("profit_usd", Decimal("0")),
                    gas_cost_usd=result.get("gas_cost_usd", Decimal("0")),
                    execution_time=execution_time,
                    transaction_hashes=result.get("transaction_hashes", []),
                    error=result.get("error")
                )
            else:
                raise ValueError("Service does not support triangular arbitrage")
                
        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"Triangular execution failed: {e}")
            
            return ExecutionResult(
                opportunity_id=opportunity.id,
                success=False,
                profit_usd=Decimal("0"),
                gas_cost_usd=Decimal("0"),
                execution_time=execution_time,
                error=str(e)
            )
    
    async def _execute_flash_loan(
        self,
        execution_id: str,
        service: Any,
        opportunity: ArbitrageOpportunity,
        plan: ExecutionPlan
    ) -> ExecutionResult:
        """Execute flash loan arbitrage"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            self.active_executions[execution_id]["status"] = ExecutionStatus.EXECUTING
            
            # Execute through service's flash loan engine
            if hasattr(service, 'flash_loan'):
                result = await service.flash_loan.execute_opportunity(opportunity)
                
                execution_time = asyncio.get_event_loop().time() - start_time
                
                return ExecutionResult(
                    opportunity_id=opportunity.id,
                    success=result.get("success", False),
                    profit_usd=result.get("profit_usd", Decimal("0")),
                    gas_cost_usd=result.get("gas_cost_usd", Decimal("0")),
                    execution_time=execution_time,
                    transaction_hashes=result.get("transaction_hashes", []),
                    error=result.get("error")
                )
            else:
                raise ValueError("Service does not support flash loan arbitrage")
                
        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"Flash loan execution failed: {e}")
            
            return ExecutionResult(
                opportunity_id=opportunity.id,
                success=False,
                profit_usd=Decimal("0"),
                gas_cost_usd=Decimal("0"),
                execution_time=execution_time,
                error=str(e)
            )
    
    async def _execution_monitor(self) -> None:
        """Monitor active executions for timeouts"""
        while True:
            try:
                current_time = datetime.now()
                timed_out_executions = []
                
                for execution_id, execution_data in self.active_executions.items():
                    start_time = execution_data["start_time"]
                    timeout = timedelta(seconds=self.config["execution_timeout"])
                    
                    if current_time - start_time > timeout:
                        timed_out_executions.append(execution_id)
                
                # Handle timeouts
                for execution_id in timed_out_executions:
                    logger.warning(f"Execution {execution_id} timed out")
                    self.active_executions[execution_id]["status"] = ExecutionStatus.FAILED
                    
                    # Create timeout result
                    execution_data = self.active_executions[execution_id]
                    timeout_result = ExecutionResult(
                        opportunity_id=execution_data["opportunity"].id,
                        success=False,
                        profit_usd=Decimal("0"),
                        gas_cost_usd=Decimal("0"),
                        execution_time=self.config["execution_timeout"],
                        error="Execution timeout"
                    )
                    
                    self.execution_history.append(timeout_result)
                    await self._update_metrics(timeout_result)
                    
                    del self.active_executions[execution_id]
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in execution monitor: {e}")
                await asyncio.sleep(30)
    
    async def _update_metrics(self, result: ExecutionResult) -> None:
        """Update execution metrics"""
        self.metrics.total_executions += 1
        
        if result.success:
            self.metrics.successful_executions += 1
            self.metrics.total_profit_usd += result.profit_usd
        else:
            self.metrics.failed_executions += 1
        
        self.metrics.total_gas_cost_usd += result.gas_cost_usd
        
        # Update averages
        if self.metrics.total_executions > 0:
            self.metrics.success_rate = (
                self.metrics.successful_executions / self.metrics.total_executions * 100
            )
        
        # Update average execution time
        if self.execution_history:
            total_time = sum(r.execution_time for r in self.execution_history)
            self.metrics.average_execution_time = total_time / len(self.execution_history)
    
    async def _metrics_updater(self) -> None:
        """Periodically update metrics"""
        while True:
            try:
                # Clean old history (keep last 1000 executions)
                if len(self.execution_history) > 1000:
                    self.execution_history = self.execution_history[-1000:]
                
                await asyncio.sleep(60)  # Update every minute
                
            except Exception as e:
                logger.error(f"Error in metrics updater: {e}")
                await asyncio.sleep(60)
    
    async def get_execution_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get status of specific execution"""
        return self.active_executions.get(execution_id)
    
    async def get_active_executions(self) -> Dict[str, Dict[str, Any]]:
        """Get all active executions"""
        return self.active_executions.copy()
    
    async def get_metrics(self) -> ExecutionMetrics:
        """Get execution metrics"""
        return self.metrics
    
    async def cancel_execution(self, execution_id: str) -> bool:
        """Cancel an active execution"""
        if execution_id in self.active_executions:
            self.active_executions[execution_id]["status"] = ExecutionStatus.CANCELLED
            logger.info(f"Cancelled execution {execution_id}")
            return True
        return False
    
    async def get_execution_history(
        self, 
        limit: int = 100, 
        success_only: bool = False
    ) -> List[ExecutionResult]:
        """Get execution history"""
        history = self.execution_history[-limit:] if limit else self.execution_history
        
        if success_only:
            history = [r for r in history if r.success]
        
        return history