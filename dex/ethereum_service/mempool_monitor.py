import asyncio
import logging
import json
from decimal import Decimal
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
import websockets
import sys
import os

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from models.arbitrage_models import ArbitrageOpportunity

from .engine import EthereumEngine
from .config import EthereumConfig

logger = logging.getLogger(__name__)

class EthereumMempoolMonitor:
    """Monitor Ethereum mempool for MEV/backrun opportunities"""
    
    def __init__(self, engine: EthereumEngine, config: EthereumConfig):
        self.engine = engine
        self.config = config
        self.websocket = None
        self.is_monitoring = False
        self.pending_txs = {}
        self.opportunity_callbacks: List[Callable] = []
        
    async def initialize(self):
        """Initialize mempool monitoring"""
        if not self.config.MEMPOOL_MONITOR_ENABLED:
            logger.info("Mempool monitoring disabled")
            return
            
        logger.info("Initializing Ethereum mempool monitor...")
        await self._connect_websocket()
        
    async def start_monitoring(self):
        """Start monitoring mempool for opportunities"""
        if not self.config.MEMPOOL_MONITOR_ENABLED:
            return
            
        self.is_monitoring = True
        logger.info("Starting mempool monitoring...")
        
        try:
            await self._monitor_pending_transactions()
        except Exception as e:
            logger.error(f"Error in mempool monitoring: {e}")
            self.is_monitoring = False
    
    async def stop_monitoring(self):
        """Stop mempool monitoring"""
        self.is_monitoring = False
        if self.websocket:
            await self.websocket.close()
        logger.info("Mempool monitoring stopped")
    
    def add_opportunity_callback(self, callback: Callable):
        """Add callback for when opportunities are found"""
        self.opportunity_callbacks.append(callback)
    
    async def _connect_websocket(self):
        """Connect to WebSocket for real-time mempool data"""
        try:
            if not self.config.WSS_URL or "YOUR_KEY" in self.config.WSS_URL:
                logger.warning("WebSocket URL not configured for mempool monitoring")
                return
                
            self.websocket = await websockets.connect(self.config.WSS_URL)
            
            # Subscribe to pending transactions
            subscription = {
                "id": 1,
                "method": "eth_subscribe",
                "params": ["newPendingTransactions"]
            }
            await self.websocket.send(json.dumps(subscription))
            
            response = await self.websocket.recv()
            logger.info(f"Mempool subscription response: {response}")
            
        except Exception as e:
            logger.error(f"Error connecting to mempool WebSocket: {e}")
    
    async def _monitor_pending_transactions(self):
        """Monitor pending transactions for arbitrage opportunities"""
        try:
            while self.is_monitoring and self.websocket:
                message = await self.websocket.recv()
                data = json.loads(message)
                
                if "params" in data:
                    tx_hash = data["params"]["result"]
                    await self._analyze_pending_transaction(tx_hash)
                    
        except Exception as e:
            logger.error(f"Error monitoring pending transactions: {e}")
    
    async def _analyze_pending_transaction(self, tx_hash: str):
        """Analyze a pending transaction for backrun opportunities"""
        try:
            # Get transaction details
            tx_data = await self._get_transaction_data(tx_hash)
            if not tx_data:
                return
            
            # Check if it's a DEX transaction
            if not self._is_dex_transaction(tx_data):
                return
            
            # Analyze for sandwich/backrun opportunity
            opportunity = await self._detect_mev_opportunity(tx_data)
            if opportunity:
                logger.info(f"MEV opportunity detected: {opportunity.opportunity_id}")
                
                # Notify callbacks
                for callback in self.opportunity_callbacks:
                    try:
                        await callback(opportunity)
                    except Exception as e:
                        logger.error(f"Error in opportunity callback: {e}")
                        
        except Exception as e:
            logger.error(f"Error analyzing pending transaction {tx_hash}: {e}")
    
    async def _get_transaction_data(self, tx_hash: str) -> Optional[Dict]:
        """Get transaction data from mempool"""
        try:
            # In production, this would get full transaction details
            # For now, return mock data
            return {
                "hash": tx_hash,
                "to": self.config.UNISWAP_V2_ROUTER,
                "value": "1000000000000000000",  # 1 ETH
                "gasPrice": "20000000000",       # 20 gwei
                "data": "0x7ff36ab5..."         # Swap function call
            }
        except Exception as e:
            logger.error(f"Error getting transaction data for {tx_hash}: {e}")
            return None
    
    def _is_dex_transaction(self, tx_data: Dict) -> bool:
        """Check if transaction is a DEX swap"""
        dex_addresses = {
            self.config.UNISWAP_V2_ROUTER.lower(),
            self.config.UNISWAP_V3_ROUTER.lower(),
            self.config.SUSHISWAP_ROUTER.lower()
        }
        
        to_address = tx_data.get("to", "").lower()
        return to_address in dex_addresses
    
    async def _detect_mev_opportunity(self, tx_data: Dict) -> Optional[ArbitrageOpportunity]:
        """Detect MEV/backrun opportunity from transaction"""
        try:
            # Analyze the transaction for potential price impact
            estimated_impact = await self._estimate_price_impact(tx_data)
            
            if estimated_impact < self.config.MIN_MEV_OPPORTUNITY_USD:
                return None
            
            # Create MEV opportunity
            return ArbitrageOpportunity(
                opportunity_id=f"mempool_{tx_data['hash']}_{int(datetime.now().timestamp())}",
                strategy_type="mempool_backrun",
                chain="ethereum",
                profit_percentage=Decimal("0.5"),  # Estimated
                profit_amount_usd=estimated_impact,
                gas_cost_usd=Decimal("30"),       # Estimated gas cost
                net_profit_usd=estimated_impact - Decimal("30"),
                detected_at=datetime.now(),
                target_tx_hash=tx_data["hash"],
                backrun_strategy="price_impact_arbitrage"
            )
            
        except Exception as e:
            logger.error(f"Error detecting MEV opportunity: {e}")
            return None
    
    async def _estimate_price_impact(self, tx_data: Dict) -> Decimal:
        """Estimate price impact of the transaction"""
        try:
            # Simplified price impact calculation
            # In production, this would decode the transaction data
            # and calculate actual price impact based on pool reserves
            
            value_eth = int(tx_data.get("value", "0")) / 1e18
            
            # Rough estimate: larger trades = more impact
            if value_eth > 10:
                return Decimal("200")  # $200 opportunity
            elif value_eth > 1:
                return Decimal("50")   # $50 opportunity
            else:
                return Decimal("10")   # $10 opportunity
                
        except Exception as e:
            logger.error(f"Error estimating price impact: {e}")
            return Decimal("0")
    
    async def execute_backrun(self, opportunity: ArbitrageOpportunity) -> Dict[str, Any]:
        """Execute a backrun strategy"""
        try:
            logger.info(f"Executing backrun for: {opportunity.target_tx_hash}")
            
            # This would:
            # 1. Wait for target transaction to be included
            # 2. Submit backrun transaction with higher gas price
            # 3. Capture the price impact/arbitrage
            
            # Placeholder implementation
            return {
                "status": "success",
                "tx_hash": "0x789...",
                "profit_realized": str(opportunity.profit_amount_usd),
                "gas_used": 180000
            }
            
        except Exception as e:
            logger.error(f"Error executing backrun: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }