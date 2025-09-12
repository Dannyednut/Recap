import logging
import os
import sys
from typing import Optional

# Add root directory to path to import shared_telegram_manager
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from shared_telegram_manager import telegram_manager

from dex.shared.logger import get_logger
from dex.shared.models.arbitrage_models import ArbitrageOpportunity, ExecutionResult

logger = get_logger(__name__)


class DEXTelegramNotifier:
    """
    Telegram notifier for DEX arbitrage trade results.
    Uses the shared Telegram bot manager to prevent multiple bot instances.
    Only sends notifications for completed trades since DEX uses flash loans (atomic execution).
    """
    
    def __init__(self, chat_id: Optional[str] = None):
        # Use the shared telegram manager instead of creating a new bot
        self.telegram_manager = telegram_manager

    async def send_trade_result(self, opportunity: ArbitrageOpportunity, result: ExecutionResult):
        """
        Send notification for completed DEX arbitrage trade.
        
        Args:
            opportunity: The arbitrage opportunity that was executed
            result: The execution result
        """
        if not self.telegram_manager.is_available():
            return
            
        try:
            # Convert opportunity and result to dict format for the manager
            opportunity_data = {
                'strategy_type': getattr(opportunity, 'strategy_type', 'unknown'),
                'chain_id': getattr(opportunity, 'chain_id', 1),
                'token_symbol': getattr(opportunity, 'token_symbol', None),
                'buy_dex': getattr(opportunity, 'buy_dex', None),
                'sell_dex': getattr(opportunity, 'sell_dex', None),
                'amount': getattr(opportunity, 'amount', 0),
                'path': getattr(opportunity, 'path', None)
            }
            
            result_data = {
                'success': getattr(result, 'success', False),
                'profit_usd': getattr(result, 'profit_usd', 0),
                'gas_cost': getattr(result, 'gas_cost', 0),
                'transaction_hash': getattr(result, 'transaction_hash', None),
                'error_message': getattr(result, 'error_message', None),
                'timestamp': getattr(result, 'timestamp', None)
            }
            
            success = await self.telegram_manager.send_dex_trade_result(opportunity_data, result_data)
            if success:
                logger.info(f"Sent DEX trade result notification to Telegram")
            
        except Exception as e:
            logger.error(f"Failed to send DEX trade result to Telegram: {e}")

    async def close(self):
        """Close the bot session - delegated to shared manager."""
        await self.telegram_manager.close()
