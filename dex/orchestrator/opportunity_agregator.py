import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass
from datetime import datetime, timedelta
import json

# Shared imports
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from models.arbitrage_models import ArbitrageOpportunity, CrossChainOpportunity

logger = logging.getLogger(__name__)

@dataclass
class OpportunityMetrics:
    total_opportunities: int
    profitable_opportunities: int
    average_profit_usd: Decimal
    max_profit_usd: Decimal
    average_execution_time: float
    success_rate: float

class OpportunityAggregator:
    """Aggregates and filters arbitrage opportunities from multiple chains"""
    
    def __init__(self):
        self.opportunity_history: List[ArbitrageOpportunity] = []
        self.cross_chain_opportunities: List[CrossChainOpportunity] = []
        self.profitability_cache: Dict[str, Decimal] = {}
        
        # Configuration
        self.config = {
            "min_profit_threshold_usd": 50.0,
            "max_gas_cost_percentage": 30.0,  # Max gas cost as % of profit
            "min_liquidity_usd": 10000.0,
            "max_price_impact": 2.0,  # Max 2% price impact
            "opportunity_ttl": 60,  # seconds
            "history_retention": 3600  # 1 hour
        }
        
        # Metrics tracking
        self.metrics: OpportunityMetrics = OpportunityMetrics(
            total_opportunities=0,
            profitable_opportunities=0,
            average_profit_usd=Decimal("0"),
            max_profit_usd=Decimal("0"),
            average_execution_time=0.0,
            success_rate=0.0
        )
    
    async def initialize(self) -> None:
        """Initialize opportunity aggregator"""
        logger.info("Initializing Opportunity Aggregator...")
        
        # Start background tasks
        asyncio.create_task(self._cleanup_expired_opportunities())
        asyncio.create_task(self._cross_chain_analyzer())
        asyncio.create_task(self._metrics_updater())
        
        logger.info("Opportunity Aggregator initialized")
    
    async def process_opportunities(
        self, 
        raw_opportunities: List[ArbitrageOpportunity]
    ) -> List[ArbitrageOpportunity]:
        """Process and filter raw opportunities"""
        try:
            logger.debug(f"Processing {len(raw_opportunities)} raw opportunities")
            
            # Filter and validate opportunities
            filtered_opportunities = []
            
            for opportunity in raw_opportunities:
                if await self._validate_opportunity(opportunity):
                    # Enhance opportunity with additional data
                    enhanced_opportunity = await self._enhance_opportunity(opportunity)
                    if enhanced_opportunity:
                        filtered_opportunities.append(enhanced_opportunity)
            
            # Sort by profitability
            filtered_opportunities.sort(
                key=lambda x: x.profit_usd, 
                reverse=True
            )
            
            # Update history and cache
            self.opportunity_history.extend(filtered_opportunities)
            await self._update_profitability_cache(filtered_opportunities)
            
            logger.info(f"Processed {len(filtered_opportunities)} profitable opportunities")
            return filtered_opportunities
            
        except Exception as e:
            logger.error(f"Error processing opportunities: {e}")
            return []
    
    async def _validate_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        """Validate if opportunity meets criteria"""
        try:
            # Check minimum profit threshold
            if opportunity.profit_usd < Decimal(str(self.config["min_profit_threshold_usd"])):
                return False
            
            # Check gas cost ratio
            if opportunity.gas_cost_usd > 0:
                gas_percentage = (opportunity.gas_cost_usd / opportunity.profit_usd) * 100
                if gas_percentage > self.config["max_gas_cost_percentage"]:
                    return False
            
            # Check liquidity requirements
            if opportunity.total_liquidity_usd < Decimal(str(self.config["min_liquidity_usd"])):
                return False
            
            # Check price impact
            if opportunity.price_impact > self.config["max_price_impact"]:
                return False
            
            # Check opportunity freshness
            if hasattr(opportunity, 'timestamp'):
                age_seconds = (datetime.now() - opportunity.timestamp).total_seconds()
                if age_seconds > self.config["opportunity_ttl"]:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating opportunity: {e}")
            return False
    
    async def _enhance_opportunity(
        self, 
        opportunity: ArbitrageOpportunity
    ) -> Optional[ArbitrageOpportunity]:
        """Enhance opportunity with additional data"""
        try:
            # Calculate risk score
            risk_score = await self._calculate_risk_score(opportunity)
            opportunity.risk_score = risk_score
            
            # Calculate execution priority
            priority = await self._calculate_priority(opportunity)
            opportunity.priority = priority
            
            # Add profitability confidence
            confidence = await self._calculate_confidence(opportunity)
            opportunity.confidence = confidence
            
            return opportunity
            
        except Exception as e:
            logger.error(f"Error enhancing opportunity: {e}")
            return opportunity
    
    async def _calculate_risk_score(self, opportunity: ArbitrageOpportunity) -> float:
        """Calculate risk score for opportunity (0-100, lower is better)"""
        risk_factors = []
        
        # Gas cost risk
        if opportunity.gas_cost_usd > 0:
            gas_ratio = float(opportunity.gas_cost_usd / opportunity.profit_usd)
            risk_factors.append(gas_ratio * 30)  # Weight: 30
        
        # Price impact risk
        risk_factors.append(opportunity.price_impact * 10)  # Weight: 10
        
        # Liquidity risk
        if opportunity.total_liquidity_usd > 0:
            liquidity_score = min(50000, float(opportunity.total_liquidity_usd)) / 50000
            risk_factors.append((1 - liquidity_score) * 20)  # Weight: 20
        
        # Chain congestion risk (placeholder)
        chain_risk = 10  # Would be calculated based on network conditions
        risk_factors.append(chain_risk)
        
        return min(100, sum(risk_factors))
    
    async def _calculate_priority(self, opportunity: ArbitrageOpportunity) -> int:
        """Calculate execution priority (1-10, higher is better)"""
        # Base priority on profit
        profit_score = min(10, float(opportunity.profit_usd) / 100)
        
        # Adjust for risk
        risk_adjustment = (100 - opportunity.risk_score) / 100
        
        # Adjust for confidence
        confidence_adjustment = opportunity.confidence / 100
        
        priority = profit_score * risk_adjustment * confidence_adjustment
        return max(1, min(10, int(priority * 10)))
    
    async def _calculate_confidence(self, opportunity: ArbitrageOpportunity) -> float:
        """Calculate confidence in opportunity (0-100)"""
        confidence_factors = []
        
        # Historical success rate for similar opportunities
        historical_success = await self._get_historical_success_rate(opportunity)
        confidence_factors.append(historical_success * 0.4)
        
        # Liquidity depth confidence
        liquidity_confidence = min(100, float(opportunity.total_liquidity_usd) / 100000 * 100)
        confidence_factors.append(liquidity_confidence * 0.3)
        
        # Gas price stability
        gas_confidence = 80  # Would be calculated based on gas price volatility
        confidence_factors.append(gas_confidence * 0.2)
        
        # Market conditions
        market_confidence = 75  # Would be calculated based on market volatility
        confidence_factors.append(market_confidence * 0.1)
        
        return sum(confidence_factors)
    
    async def _get_historical_success_rate(self, opportunity: ArbitrageOpportunity) -> float:
        """Get historical success rate for similar opportunities"""
        # This would analyze historical data
        # For now, return a reasonable default
        return 85.0
    
    async def _update_profitability_cache(
        self, 
        opportunities: List[ArbitrageOpportunity]
    ) -> None:
        """Update profitability cache for fast lookups"""
        for opportunity in opportunities:
            cache_key = f"{opportunity.chain}_{opportunity.type}_{opportunity.token_a}_{opportunity.token_b}"
            self.profitability_cache[cache_key] = opportunity.profit_usd
    
    async def _cleanup_expired_opportunities(self) -> None:
        """Clean up expired opportunities from history"""
        while True:
            try:
                cutoff_time = datetime.now() - timedelta(seconds=self.config["history_retention"])
                
                # Clean up history
                self.opportunity_history = [
                    op for op in self.opportunity_history
                    if hasattr(op, 'timestamp') and op.timestamp > cutoff_time
                ]
                
                # Clean up cache
                expired_keys = []
                for key in self.profitability_cache.keys():
                    # Simple expiration logic - would be enhanced with timestamps
                    if len(self.profitability_cache) > 1000:  # Max cache size
                        expired_keys.append(key)
                
                for key in expired_keys[:100]:  # Remove oldest 100 entries
                    del self.profitability_cache[key]
                
                await asyncio.sleep(300)  # Clean up every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(300)
    
    async def _cross_chain_analyzer(self) -> None:
        """Analyze cross-chain arbitrage opportunities"""
        while True:
            try:
                # Look for arbitrage opportunities across different chains
                # This would compare prices between Ethereum, BSC, Polygon, etc.
                
                # Group opportunities by token pair
                token_pairs = {}
                for opportunity in self.opportunity_history[-100:]:  # Recent opportunities
                    pair_key = f"{opportunity.token_a}_{opportunity.token_b}"
                    if pair_key not in token_pairs:
                        token_pairs[pair_key] = []
                    token_pairs[pair_key].append(opportunity)
                
                # Find cross-chain opportunities
                for pair_key, opportunities in token_pairs.items():
                    if len(opportunities) > 1:
                        # Check for price differences across chains
                        chain_prices = {}
                        for op in opportunities:
                            if op.chain not in chain_prices:
                                chain_prices[op.chain] = []
                            chain_prices[op.chain].append(op.price_difference)
                        
                        # If we have multiple chains for the same pair
                        if len(chain_prices) > 1:
                            await self._create_cross_chain_opportunity(pair_key, chain_prices)
                
                await asyncio.sleep(60)  # Analyze every minute
                
            except Exception as e:
                logger.error(f"Error in cross-chain analyzer: {e}")
                await asyncio.sleep(60)
    
    async def _create_cross_chain_opportunity(
        self, 
        pair_key: str, 
        chain_prices: Dict[str, List[Decimal]]
    ) -> None:
        """Create cross-chain arbitrage opportunity"""
        try:
            # Find the chains with highest and lowest prices
            avg_prices = {
                chain: sum(prices) / len(prices) 
                for chain, prices in chain_prices.items()
            }
            
            min_chain = min(avg_prices, key=avg_prices.get)
            max_chain = max(avg_prices, key=avg_prices.get)
            
            price_diff = avg_prices[max_chain] - avg_prices[min_chain]
            
            # If price difference is significant
            if price_diff > Decimal("0.01"):  # 1% difference
                cross_chain_op = CrossChainOpportunity(
                    id=f"cross_{pair_key}_{datetime.now().timestamp()}",
                    buy_chain=min_chain,
                    sell_chain=max_chain,
                    token_pair=pair_key,
                    price_difference=price_diff,
                    estimated_profit=price_diff * Decimal("1000"),  # Assuming $1000 trade
                    confidence=75.0,
                    timestamp=datetime.now()
                )
                
                self.cross_chain_opportunities.append(cross_chain_op)
                logger.info(f"Found cross-chain opportunity: {cross_chain_op.id}")
        
        except Exception as e:
            logger.error(f"Error creating cross-chain opportunity: {e}")
    
    async def _metrics_updater(self) -> None:
        """Update aggregator metrics"""
        while True:
            try:
                if self.opportunity_history:
                    profitable_ops = [
                        op for op in self.opportunity_history 
                        if op.profit_usd > 0
                    ]
                    
                    self.metrics.total_opportunities = len(self.opportunity_history)
                    self.metrics.profitable_opportunities = len(profitable_ops)
                    
                    if profitable_ops:
                        profits = [float(op.profit_usd) for op in profitable_ops]
                        self.metrics.average_profit_usd = Decimal(str(sum(profits) / len(profits)))
                        self.metrics.max_profit_usd = Decimal(str(max(profits)))
                    
                    self.metrics.success_rate = (
                        len(profitable_ops) / len(self.opportunity_history) * 100
                        if self.opportunity_history else 0
                    )
                
                await asyncio.sleep(30)  # Update every 30 seconds
                
            except Exception as e:
                logger.error(f"Error updating metrics: {e}")
                await asyncio.sleep(30)
    
    async def get_metrics(self) -> OpportunityMetrics:
        """Get current aggregator metrics"""
        return self.metrics
    
    async def get_cross_chain_opportunities(self) -> List[CrossChainOpportunity]:
        """Get current cross-chain opportunities"""
        return self.cross_chain_opportunities.copy()
    
    async def get_opportunity_history(
        self, 
        limit: int = 100, 
        chain: Optional[str] = None
    ) -> List[ArbitrageOpportunity]:
        """Get recent opportunity history"""
        history = self.opportunity_history[-limit:] if limit else self.opportunity_history
        
        if chain:
            history = [op for op in history if op.chain == chain]
        
        return history