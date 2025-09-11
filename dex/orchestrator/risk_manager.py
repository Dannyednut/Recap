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
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from models.arbitrage_models import ArbitrageOpportunity

logger = logging.getLogger(__name__)

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class RiskAssessment:
    opportunity_id: str
    overall_risk: RiskLevel
    risk_score: float  # 0-100
    risk_factors: Dict[str, float]
    recommendations: List[str]
    max_position_size: Decimal
    confidence_level: float

@dataclass
class PortfolioLimits:
    max_single_trade_usd: Decimal
    max_daily_volume_usd: Decimal
    max_gas_cost_percentage: float
    max_slippage_tolerance: float
    max_concurrent_trades: int
    min_liquidity_ratio: float

class RiskManager:
    """Comprehensive risk management for DEX arbitrage operations"""
    
    def __init__(self):
        # Risk configuration
        self.limits = PortfolioLimits(
            max_single_trade_usd=Decimal("5000"),
            max_daily_volume_usd=Decimal("50000"),
            max_gas_cost_percentage=25.0,  # 25% of profit
            max_slippage_tolerance=2.0,    # 2%
            max_concurrent_trades=3,
            min_liquidity_ratio=5.0        # Trade size should be <20% of liquidity
        )
        
        # Risk tracking
        self.daily_volume: Dict[str, Decimal] = {}  # chain -> volume
        self.active_trades: Dict[str, ArbitrageOpportunity] = {}
        self.risk_history: List[RiskAssessment] = []
        self.blacklisted_tokens: List[str] = []
        self.blacklisted_exchanges: List[str] = []
        
        # Market conditions
        self.market_volatility: Dict[str, float] = {}  # token -> volatility
        self.gas_price_trends: Dict[str, List[Tuple[datetime, float]]] = {}
        self.network_congestion: Dict[str, float] = {}  # chain -> congestion level
        
        # Performance tracking
        self.success_rates: Dict[str, float] = {}  # opportunity_type -> success_rate
        self.profit_distributions: Dict[str, List[Decimal]] = {}
        
    async def initialize(self) -> None:
        """Initialize risk manager"""
        logger.info("Initializing Risk Manager...")
        
        # Start background risk monitoring
        asyncio.create_task(self._market_monitor())
        asyncio.create_task(self._volatility_tracker())
        asyncio.create_task(self._daily_reset())
        
        # Load risk configuration from environment
        await self._load_risk_configuration()
        
        logger.info("Risk Manager initialized")
    
    async def validate_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        """Validate if opportunity passes risk checks"""
        try:
            # Perform comprehensive risk assessment
            assessment = await self.assess_opportunity_risk(opportunity)
            
            # Check if risk level is acceptable
            if assessment.overall_risk == RiskLevel.CRITICAL:
                logger.warning(f"Rejecting opportunity {opportunity.id}: Critical risk level")
                return False
            
            # Check position size limits
            if not await self._check_position_limits(opportunity):
                logger.warning(f"Rejecting opportunity {opportunity.id}: Position size limits")
                return False
            
            # Check daily volume limits
            if not await self._check_daily_limits(opportunity):
                logger.warning(f"Rejecting opportunity {opportunity.id}: Daily volume limits")
                return False
            
            # Check concurrent trade limits
            if len(self.active_trades) >= self.limits.max_concurrent_trades:
                logger.warning(f"Rejecting opportunity {opportunity.id}: Max concurrent trades")
                return False
            
            # Check blacklists
            if await self._is_blacklisted(opportunity):
                logger.warning(f"Rejecting opportunity {opportunity.id}: Blacklisted asset/exchange")
                return False
            
            # Store assessment for tracking
            self.risk_history.append(assessment)
            
            logger.info(f"Opportunity {opportunity.id} passed risk validation (Risk: {assessment.overall_risk.value}, Score: {assessment.risk_score})")
            return True
            
        except Exception as e:
            logger.error(f"Error validating opportunity risk: {e}")
            return False
    
    async def assess_opportunity_risk(self, opportunity: ArbitrageOpportunity) -> RiskAssessment:
        """Comprehensive risk assessment for opportunity"""
        try:
            risk_factors = {}
            
            # 1. Profit Risk Assessment
            profit_risk = await self._assess_profit_risk(opportunity)
            risk_factors["profit_risk"] = profit_risk
            
            # 2. Liquidity Risk Assessment
            liquidity_risk = await self._assess_liquidity_risk(opportunity)
            risk_factors["liquidity_risk"] = liquidity_risk
            
            # 3. Gas Cost Risk Assessment
            gas_risk = await self._assess_gas_risk(opportunity)
            risk_factors["gas_risk"] = gas_risk
            
            # 4. Market Risk Assessment
            market_risk = await self._assess_market_risk(opportunity)
            risk_factors["market_risk"] = market_risk
            
            # 5. Technical Risk Assessment
            technical_risk = await self._assess_technical_risk(opportunity)
            risk_factors["technical_risk"] = technical_risk
            
            # 6. Execution Risk Assessment
            execution_risk = await self._assess_execution_risk(opportunity)
            risk_factors["execution_risk"] = execution_risk
            
            # Calculate overall risk score (weighted average)
            weights = {
                "profit_risk": 0.25,
                "liquidity_risk": 0.20,
                "gas_risk": 0.15,
                "market_risk": 0.15,
                "technical_risk": 0.15,
                "execution_risk": 0.10
            }
            
            overall_score = sum(
                risk_factors[factor] * weights[factor] 
                for factor in weights.keys()
            )
            
            # Determine risk level
            if overall_score < 25:
                risk_level = RiskLevel.LOW
            elif overall_score < 50:
                risk_level = RiskLevel.MEDIUM
            elif overall_score < 75:
                risk_level = RiskLevel.HIGH
            else:
                risk_level = RiskLevel.CRITICAL
            
            # Generate recommendations
            recommendations = await self._generate_recommendations(risk_factors, opportunity)
            
            # Calculate max position size based on risk
            max_position = await self._calculate_max_position_size(opportunity, overall_score)
            
            # Calculate confidence level
            confidence = await self._calculate_confidence(opportunity, risk_factors)
            
            return RiskAssessment(
                opportunity_id=opportunity.id,
                overall_risk=risk_level,
                risk_score=overall_score,
                risk_factors=risk_factors,
                recommendations=recommendations,
                max_position_size=max_position,
                confidence_level=confidence
            )
            
        except Exception as e:
            logger.error(f"Error assessing opportunity risk: {e}")
            # Return high-risk assessment on error
            return RiskAssessment(
                opportunity_id=opportunity.id,
                overall_risk=RiskLevel.CRITICAL,
                risk_score=100.0,
                risk_factors={"error": 100.0},
                recommendations=["Manual review required due to assessment error"],
                max_position_size=Decimal("0"),
                confidence_level=0.0
            )
    
    async def _assess_profit_risk(self, opportunity: ArbitrageOpportunity) -> float:
        """Assess profit-related risks"""
        risk_score = 0.0
        
        # Check profit margin
        if opportunity.profit_usd < Decimal("10"):
            risk_score += 30  # Low profit, high risk
        elif opportunity.profit_usd < Decimal("50"):
            risk_score += 15  # Medium profit
        
        # Check profit-to-investment ratio
        if hasattr(opportunity, 'amount_in') and opportunity.amount_in > 0:
            profit_ratio = float(opportunity.profit_usd / (opportunity.amount_in * Decimal("0.01")))  # Assume 1% of amount_in as reference
            if profit_ratio < 2.0:  # Less than 2% profit margin
                risk_score += 25
        
        return min(100, risk_score)
    
    async def _assess_liquidity_risk(self, opportunity: ArbitrageOpportunity) -> float:
        """Assess liquidity-related risks"""
        risk_score = 0.0
        
        # Check total liquidity
        if opportunity.total_liquidity_usd < Decimal("10000"):
            risk_score += 40  # Very low liquidity
        elif opportunity.total_liquidity_usd < Decimal("50000"):
            risk_score += 20  # Low liquidity
        
        # Check liquidity ratio (trade size vs available liquidity)
        if hasattr(opportunity, 'amount_in') and opportunity.amount_in > 0:
            if opportunity.total_liquidity_usd > 0:
                liquidity_ratio = float(opportunity.amount_in / opportunity.total_liquidity_usd) * 100
                if liquidity_ratio > 20:  # Trade is >20% of liquidity
                    risk_score += 30
                elif liquidity_ratio > 10:  # Trade is >10% of liquidity
                    risk_score += 15
        
        return min(100, risk_score)
    
    async def _assess_gas_risk(self, opportunity: ArbitrageOpportunity) -> float:
        """Assess gas cost risks"""
        risk_score = 0.0
        
        # Check gas cost as percentage of profit
        if opportunity.gas_cost_usd > 0 and opportunity.profit_usd > 0:
            gas_percentage = float(opportunity.gas_cost_usd / opportunity.profit_usd) * 100
            
            if gas_percentage > 50:  # Gas cost >50% of profit
                risk_score += 50
            elif gas_percentage > 30:  # Gas cost >30% of profit
                risk_score += 30
            elif gas_percentage > 15:  # Gas cost >15% of profit
                risk_score += 15
        
        # Check absolute gas cost
        if opportunity.gas_cost_usd > Decimal("100"):
            risk_score += 20  # High absolute gas cost
        
        return min(100, risk_score)
    
    async def _assess_market_risk(self, opportunity: ArbitrageOpportunity) -> float:
        """Assess market condition risks"""
        risk_score = 0.0
        
        # Check token volatility
        tokens = [opportunity.token_a, opportunity.token_b]
        if hasattr(opportunity, 'token_c'):
            tokens.append(opportunity.token_c)
        
        for token in tokens:
            volatility = self.market_volatility.get(token, 0.1)  # Default 10% volatility
            if volatility > 0.3:  # >30% volatility
                risk_score += 20
            elif volatility > 0.2:  # >20% volatility
                risk_score += 10
        
        # Check network congestion
        chain_congestion = self.network_congestion.get(opportunity.chain, 0.5)
        if chain_congestion > 0.8:  # High congestion
            risk_score += 25
        elif chain_congestion > 0.6:  # Medium congestion
            risk_score += 10
        
        return min(100, risk_score)
    
    async def _assess_technical_risk(self, opportunity: ArbitrageOpportunity) -> float:
        """Assess technical execution risks"""
        risk_score = 0.0
        
        # Check price impact
        if opportunity.price_impact > 5.0:  # >5% price impact
            risk_score += 40
        elif opportunity.price_impact > 2.0:  # >2% price impact
            risk_score += 20
        
        # Check execution complexity
        if opportunity.type == "triangular":
            risk_score += 15  # More complex than simple swaps
        elif opportunity.type == "flash_loan":
            risk_score += 25  # Most complex execution
        
        return min(100, risk_score)
    
    async def _assess_execution_risk(self, opportunity: ArbitrageOpportunity) -> float:
        """Assess execution-specific risks"""
        risk_score = 0.0
        
        # Check historical success rate for similar opportunities
        opportunity_type = f"{opportunity.chain}_{opportunity.type}"
        historical_success = self.success_rates.get(opportunity_type, 0.8)  # Default 80%
        
        if historical_success < 0.5:  # <50% success rate
            risk_score += 40
        elif historical_success < 0.7:  # <70% success rate
            risk_score += 20
        
        # Check opportunity age (if available)
        if hasattr(opportunity, 'timestamp'):
            age_seconds = (datetime.now() - opportunity.timestamp).total_seconds()
            if age_seconds > 30:  # Opportunity older than 30 seconds
                risk_score += 15
        
        return min(100, risk_score)
    
    async def _generate_recommendations(
        self, 
        risk_factors: Dict[str, float], 
        opportunity: ArbitrageOpportunity
    ) -> List[str]:
        """Generate risk mitigation recommendations"""
        recommendations = []
        
        if risk_factors.get("profit_risk", 0) > 20:
            recommendations.append("Consider increasing trade size for better profit margins")
        
        if risk_factors.get("liquidity_risk", 0) > 30:
            recommendations.append("Reduce trade size due to low liquidity")
        
        if risk_factors.get("gas_risk", 0) > 25:
            recommendations.append("Monitor gas prices and consider delaying execution")
        
        if risk_factors.get("market_risk", 0) > 30:
            recommendations.append("High market volatility - consider reduced position size")
        
        if risk_factors.get("technical_risk", 0) > 30:
            recommendations.append("High price impact detected - use smaller trade size")
        
        if risk_factors.get("execution_risk", 0) > 25:
            recommendations.append("Low historical success rate - proceed with caution")
        
        return recommendations
    
    async def _calculate_max_position_size(
        self, 
        opportunity: ArbitrageOpportunity, 
        risk_score: float
    ) -> Decimal:
        """Calculate maximum recommended position size"""
        # Base position size (from config)
        base_size = self.limits.max_single_trade_usd
        
        # Risk-based adjustment
        risk_multiplier = max(0.1, (100 - risk_score) / 100)
        
        # Liquidity-based adjustment
        liquidity_multiplier = min(1.0, float(opportunity.total_liquidity_usd) / 100000)
        
        max_size = base_size * Decimal(str(risk_multiplier)) * Decimal(str(liquidity_multiplier))
        
        return max_size
    
    async def _calculate_confidence(
        self, 
        opportunity: ArbitrageOpportunity, 
        risk_factors: Dict[str, float]
    ) -> float:
        """Calculate confidence level in the opportunity"""
        # Base confidence starts at 100
        confidence = 100.0
        
        # Reduce confidence based on risk factors
        for factor, score in risk_factors.items():
            confidence -= score * 0.1  # Each risk point reduces confidence
        
        # Adjust based on historical performance
        opportunity_type = f"{opportunity.chain}_{opportunity.type}"
        historical_success = self.success_rates.get(opportunity_type, 0.8)
        confidence *= historical_success
        
        return max(0.0, min(100.0, confidence))
    
    async def _check_position_limits(self, opportunity: ArbitrageOpportunity) -> bool:
        """Check if opportunity respects position size limits"""
        if hasattr(opportunity, 'amount_in'):
            # Convert to USD value (simplified)
            trade_value_usd = opportunity.amount_in * Decimal("1000")  # Placeholder conversion
            
            return trade_value_usd <= self.limits.max_single_trade_usd
        
        return True  # Allow if we can't determine size
    
    async def _check_daily_limits(self, opportunity: ArbitrageOpportunity) -> bool:
        """Check daily volume limits"""
        today = datetime.now().date().isoformat()
        chain_key = f"{opportunity.chain}_{today}"
        
        current_volume = self.daily_volume.get(chain_key, Decimal("0"))
        
        if hasattr(opportunity, 'amount_in'):
            trade_value_usd = opportunity.amount_in * Decimal("1000")  # Placeholder conversion
            
            return current_volume + trade_value_usd <= self.limits.max_daily_volume_usd
        
        return True
    
    async def _is_blacklisted(self, opportunity: ArbitrageOpportunity) -> bool:
        """Check if opportunity involves blacklisted assets or exchanges"""
        # Check tokens
        tokens = [opportunity.token_a, opportunity.token_b]
        if hasattr(opportunity, 'token_c'):
            tokens.append(opportunity.token_c)
        
        for token in tokens:
            if token in self.blacklisted_tokens:
                return True
        
        # Check exchanges
        exchanges = [opportunity.exchange_a]
        if hasattr(opportunity, 'exchange_b'):
            exchanges.append(opportunity.exchange_b)
        
        for exchange in exchanges:
            if exchange in self.blacklisted_exchanges:
                return True
        
        return False
    
    async def _load_risk_configuration(self) -> None:
        """Load risk configuration from environment or config file"""
        # This would load from environment variables or config files
        # For now, using defaults
        logger.info("Using default risk configuration")
    
    async def _market_monitor(self) -> None:
        """Monitor market conditions"""
        while True:
            try:
                # Update market volatility data
                # This would fetch real volatility data from price feeds
                
                # Update network congestion
                # This would check network stats
                
                await asyncio.sleep(60)  # Update every minute
                
            except Exception as e:
                logger.error(f"Error in market monitor: {e}")
                await asyncio.sleep(60)
    
    async def _volatility_tracker(self) -> None:
        """Track token volatility"""
        while True:
            try:
                # Calculate volatility for tracked tokens
                # This would use price history to calculate volatility
                
                await asyncio.sleep(300)  # Update every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in volatility tracker: {e}")
                await asyncio.sleep(300)
    
    async def _daily_reset(self) -> None:
        """Reset daily tracking data"""
        while True:
            try:
                # Wait until midnight
                now = datetime.now()
                tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                sleep_seconds = (tomorrow - now).total_seconds()
                
                await asyncio.sleep(sleep_seconds)
                
                # Reset daily volume tracking
                self.daily_volume.clear()
                logger.info("Reset daily volume tracking")
                
            except Exception as e:
                logger.error(f"Error in daily reset: {e}")
                await asyncio.sleep(3600)  # Retry in 1 hour
    
    async def add_to_blacklist(self, item_type: str, item_value: str) -> None:
        """Add item to blacklist"""
        if item_type == "token":
            self.blacklisted_tokens.append(item_value)
        elif item_type == "exchange":
            self.blacklisted_exchanges.append(item_value)
        
        logger.info(f"Added {item_type} {item_value} to blacklist")
    
    async def remove_from_blacklist(self, item_type: str, item_value: str) -> None:
        """Remove item from blacklist"""
        if item_type == "token" and item_value in self.blacklisted_tokens:
            self.blacklisted_tokens.remove(item_value)
        elif item_type == "exchange" and item_value in self.blacklisted_exchanges:
            self.blacklisted_exchanges.remove(item_value)
        
        logger.info(f"Removed {item_type} {item_value} from blacklist")
    
    async def get_risk_metrics(self) -> Dict[str, Any]:
        """Get current risk metrics"""
        return {
            "active_trades": len(self.active_trades),
            "daily_volume": dict(self.daily_volume),
            "blacklisted_tokens": len(self.blacklisted_tokens),
            "blacklisted_exchanges": len(self.blacklisted_exchanges),
            "risk_assessments_today": len([
                a for a in self.risk_history 
                if hasattr(a, 'timestamp') and 
                a.timestamp.date() == datetime.now().date()
            ]) if self.risk_history and hasattr(self.risk_history[0], 'timestamp') else 0,
            "success_rates": dict(self.success_rates)
        }