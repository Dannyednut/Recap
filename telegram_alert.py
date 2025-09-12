import logging
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from cex.models import Opportunity, TradeResult
from cex.config import Config
from cex.engine import logger
from shared_telegram_manager import telegram_manager

# Simple whitelist check
def is_whitelisted_chat(chat_id):
    try:
        allowed = int(Config.TELEGRAM_CHAT_ID)
        return chat_id == allowed
    except Exception:
        return False


class TelegramNotifier:
    def __init__(self, chat_id, execution_endpoint: str = None):
        # Use the shared telegram manager instead of creating a new bot
        self.telegram_manager = telegram_manager
        self.chat_id = int(chat_id) if chat_id else None
        self.execution_endpoint = execution_endpoint or Config.EXECUTE_URL

        # Register handlers with the shared dispatcher
        if self.telegram_manager.dispatcher:
            # Accept callback queries that begin with EXECUTE_
            self.telegram_manager.dispatcher.callback_query.register(
                self.handle_execute_button, 
                lambda c: str(c.data).startswith("EXECUTE_")
            )

    async def send_opportunity_alert(self, opportunity: Opportunity, Id: str = None):
        """
        Send an opportunity alert message with inline buttons to execute trade.
        """
        if not self.telegram_manager.is_available():
            return
            
        try:
            # Convert opportunity to dict format for the manager
            opportunity_data = {
                'trading_pair': getattr(opportunity, 'trading_pair', None),
                'buy_exchange': getattr(opportunity, 'buy_exchange', None),
                'sell_exchange': getattr(opportunity, 'sell_exchange', None),
                'buy_price': getattr(opportunity, 'buy_price', 0),
                'sell_price': getattr(opportunity, 'sell_price', 0),
                'profit_percentage': getattr(opportunity, 'profit_percentage', 0),
                'profit_usd': getattr(opportunity, 'profit_usd', 0),
                'volume': getattr(opportunity, 'volume', 0),
                'detected_at': getattr(opportunity, 'detected_at', ''),
                'exchange': getattr(opportunity, 'exchange', None),
                'trading_path': getattr(opportunity, 'trading_path', None),
                'initial_amount': getattr(opportunity, 'initial_amount', 0),
                'final_amount': getattr(opportunity, 'final_amount', 0)
            }
            
            success = await self.telegram_manager.send_cex_opportunity_alert(opportunity_data, Id)
            if not success:
                logger.error("Failed to send CEX opportunity alert via shared manager")
                
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")

    def _format_opportunity_message(self, opp: Opportunity) -> str:
        if getattr(opp, 'trading_pair', None):
            text = (
                f"♻️ <b>New Cross-Exchange Opportunity Detected!</b>\n"
                f"Pair: {opp.trading_pair}\n"
                f"Buy on: {opp.buy_exchange} @ {opp.buy_price:.6f}\n"
                f"Sell on: {opp.sell_exchange} @ {opp.sell_price:.6f}\n"
                f"Profit: {opp.profit_percentage:.2f}% ({opp.profit_usd:.2f} USD)\n"
                f"Volume: {opp.volume}\n"
                f"Detected At: {opp.detected_at}"
            )
        else:
            path_str = " -> ".join(opp.trading_path or [])
            text = (
                f"🔺 <b>New Triangular Opportunity Detected!</b>\n"
                f"Exchange: {opp.exchange}\n"
                f"Path: {path_str}\n"
                f"Profit: {opp.profit_percentage:.2f}%\n"
                f"Initial Amount: {opp.initial_amount}\n"
                f"Final Amount: {opp.final_amount}\n"
                f"Detected At: {opp.detected_at}"
            )
        return text

    def _build_action_buttons(self, opp: Opportunity, Id: str = None) -> InlineKeyboardMarkup:
        opp_type = "cross" if getattr(opp, 'trading_pair', None) else "triangular"
        buttons = []
        if opp_type == "cross":
            buttons.append([
                InlineKeyboardButton(text="Execute Instant", callback_data=f"EXECUTE_{opp_type}_{Id}_instant"),
                InlineKeyboardButton(text="Execute Transfer", callback_data=f"EXECUTE_{opp_type}_{Id}_transfer")
            ])
        else:
            buttons.append([InlineKeyboardButton(text="Execute", callback_data=f"EXECUTE_{opp_type}_{Id}_default")])
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    async def handle_execute_button(self, callback_query: CallbackQuery):
        await callback_query.answer()
        chat_id = callback_query.message.chat.id

        # Whitelist chat_id
        if not is_whitelisted_chat(chat_id):
            await callback_query.message.edit_text("Unauthorized chat.")
            return

        try:
            _, opp_type, opportunity_id, strategy = callback_query.data.split("_")
            trade_type = "triangular" if opp_type == "triangular" else "cross"
            payload = {
                "type": trade_type,
                "strategy": strategy,
                "opportunity_id": opportunity_id,
                "chat_id": chat_id
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(self.execution_endpoint, json=payload, timeout=10) as resp:
                    try:
                        data = await resp.json()
                    except Exception:
                        data = {"status": "error", "message": "No json response"}

            if resp.status == 200:
                text = "✅ Trade request accepted, executing..."
            else:
                text = f"⚠️ Execution failed: {data.get('message', 'Unknown error')}"

        except Exception as e:
            logger.error(f"Error handling execute button: {e}")
            text = f"❌ Error during execution: {str(e)}"

        await callback_query.message.edit_text(text, parse_mode="HTML")

    async def send_trade_result(self, chat_id: int, trade_result: TradeResult):
        if not self.telegram_manager.is_available():
            return
            
        try:
            # Convert trade result to dict format for the manager
            trade_result_data = {
                'status': getattr(trade_result, 'status', 'unknown'),
                'message': getattr(trade_result, 'message', ''),
                'trade_id': getattr(trade_result, 'trade_id', None),
                'profit_usd': getattr(trade_result, 'profit_usd', None)
            }
            
            success = await self.telegram_manager.send_cex_trade_result(trade_result_data)
            if not success:
                logger.error("Failed to send CEX trade result via shared manager")
                
        except Exception as e:
            logger.error(f"Failed to send trade result to Telegram: {e}")

    async def start_polling(self):
        if self.telegram_manager.dispatcher:
            await self.telegram_manager.dispatcher.start_polling(self.telegram_manager.bot, skip_updates=True)
