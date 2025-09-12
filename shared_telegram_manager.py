import logging
import os
from typing import Optional, Dict, Any
from aiogram import Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio

logger = logging.getLogger(__name__)


class TelegramBotManager:
    """
    Singleton Telegram bot manager to ensure only one bot instance runs
    for both CEX and DEX services using the same bot token.
    """
    _instance: Optional['TelegramBotManager'] = None
    _bot: Optional[Bot] = None
    _dispatcher: Optional[Dispatcher] = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.chat_id = None
            self.token = None
            self._setup_bot()
            TelegramBotManager._initialized = True
    
    def _setup_bot(self):
        """Initialize the bot with token from environment"""
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            logger.warning("TELEGRAM_BOT_TOKEN not configured. Telegram notifications disabled.")
            return
            
        # Get chat ID from environment
        env_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if env_chat_id:
            self.chat_id = int(env_chat_id)
        else:
            logger.warning("TELEGRAM_CHAT_ID not configured. Telegram notifications disabled.")
            return
            
        # Create bot and dispatcher instances
        TelegramBotManager._bot = Bot(token=self.token)
        TelegramBotManager._dispatcher = Dispatcher()
        
        logger.info("Telegram bot manager initialized successfully")
    
    @property
    def bot(self) -> Optional[Bot]:
        """Get the shared bot instance"""
        return TelegramBotManager._bot
    
    @property
    def dispatcher(self) -> Optional[Dispatcher]:
        """Get the shared dispatcher instance"""
        return TelegramBotManager._dispatcher
    
    def is_available(self) -> bool:
        """Check if Telegram bot is available for use"""
        return self.bot is not None and self.chat_id is not None
    
    async def send_message(self, text: str, parse_mode: str = "HTML", reply_markup: Optional[InlineKeyboardMarkup] = None) -> bool:
        """
        Send a message via Telegram bot
        
        Args:
            text: Message text
            parse_mode: Parse mode (HTML, Markdown, etc.)
            reply_markup: Optional inline keyboard
            
        Returns:
            bool: True if message sent successfully, False otherwise
        """
        if not self.is_available():
            return False
            
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    async def send_cex_opportunity_alert(self, opportunity_data: Dict[str, Any], opportunity_id: str = None) -> bool:
        """Send CEX opportunity alert with action buttons"""
        if not self.is_available():
            return False
            
        try:
            # Format CEX opportunity message
            if opportunity_data.get('trading_pair'):
                # Cross-exchange opportunity
                text = (
                    f"♻️ <b>CEX Cross-Exchange Opportunity!</b>\n"
                    f"Pair: {opportunity_data['trading_pair']}\n"
                    f"Buy on: {opportunity_data['buy_exchange']} @ {opportunity_data['buy_price']:.6f}\n"
                    f"Sell on: {opportunity_data['sell_exchange']} @ {opportunity_data['sell_price']:.6f}\n"
                    f"Profit: {opportunity_data['profit_percentage']:.2f}% (${opportunity_data['profit_usd']:.2f})\n"
                    f"Volume: {opportunity_data['volume']}\n"
                    f"Detected At: {opportunity_data['detected_at']}"
                )
                
                # Add execution buttons
                keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="Execute Instant", callback_data=f"EXECUTE_cross_{opportunity_id}_instant"),
                    InlineKeyboardButton(text="Execute Transfer", callback_data=f"EXECUTE_cross_{opportunity_id}_transfer")
                ]])
            else:
                # Triangular opportunity
                path_str = " -> ".join(opportunity_data.get('trading_path', []))
                text = (
                    f"🔺 <b>CEX Triangular Opportunity!</b>\n"
                    f"Exchange: {opportunity_data['exchange']}\n"
                    f"Path: {path_str}\n"
                    f"Profit: {opportunity_data['profit_percentage']:.2f}%\n"
                    f"Initial Amount: {opportunity_data['initial_amount']}\n"
                    f"Final Amount: {opportunity_data['final_amount']}\n"
                    f"Detected At: {opportunity_data['detected_at']}"
                )
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="Execute", callback_data=f"EXECUTE_triangular_{opportunity_id}_default")
                ]])
            
            return await self.send_message(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Failed to send CEX opportunity alert: {e}")
            return False
    
    async def send_dex_trade_result(self, opportunity_data: Dict[str, Any], result_data: Dict[str, Any]) -> bool:
        """Send DEX trade result notification"""
        if not self.is_available():
            return False
            
        try:
            # Get strategy emoji and chain info
            strategy_type = opportunity_data.get('strategy_type', 'unknown')
            chain_id = opportunity_data.get('chain_id', 1)
            
            strategy_emoji = self._get_strategy_emoji(strategy_type)
            chain_name = self._get_chain_name(chain_id)
            
            # Status emoji
            success = result_data.get('success', False)
            status_emoji = "✅" if success else "❌"
            status_text = "SUCCESS" if success else "FAILED"
            
            # Base message
            text = (
                f"{strategy_emoji} <b>DEX Arbitrage {status_text}</b>\n"
                f"Chain: {chain_name}\n"
                f"Strategy: {strategy_type.replace('_', ' ').title()}\n"
            )
            
            # Add strategy-specific details
            if strategy_type == "cross_arbitrage":
                text += (
                    f"Token: {opportunity_data.get('token_symbol', 'Unknown')}\n"
                    f"Buy DEX: {opportunity_data.get('buy_dex', 'Unknown')}\n"
                    f"Sell DEX: {opportunity_data.get('sell_dex', 'Unknown')}\n"
                    f"Amount: {opportunity_data.get('amount', 0):.6f}\n"
                )
            elif strategy_type == "triangular_arbitrage":
                path = " → ".join(opportunity_data.get('path', [])) if opportunity_data.get('path') else "Unknown"
                text += (
                    f"Path: {path}\n"
                    f"Initial Amount: {opportunity_data.get('amount', 0):.6f}\n"
                )
            elif strategy_type == "flash_loan_arbitrage":
                text += (
                    f"Flash Loan Asset: {opportunity_data.get('token_symbol', 'Unknown')}\n"
                    f"Loan Amount: {opportunity_data.get('amount', 0):.6f}\n"
                    f"DEX Route: {opportunity_data.get('buy_dex', 'Unknown')} → {opportunity_data.get('sell_dex', 'Unknown')}\n"
                )
            
            # Add execution results
            if success:
                profit_usd = result_data.get('profit_usd', 0) or 0
                gas_cost = result_data.get('gas_cost', 0) or 0
                net_profit = profit_usd - gas_cost
                
                text += (
                    f"💰 Gross Profit: ${profit_usd:.4f}\n"
                    f"⛽ Gas Cost: ${gas_cost:.4f}\n"
                    f"📊 Net Profit: ${net_profit:.4f}\n"
                )
                
                tx_hash = result_data.get('transaction_hash')
                if tx_hash:
                    explorer_url = self._get_explorer_url(chain_id, tx_hash)
                    text += f"🔗 <a href='{explorer_url}'>View Transaction</a>\n"
            else:
                text += f"❌ Error: {result_data.get('error_message', 'Unknown error')}\n"
            
            # Add timestamp
            timestamp = result_data.get('timestamp')
            if timestamp:
                text += f"⏰ Executed: {timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            
            return await self.send_message(text)
            
        except Exception as e:
            logger.error(f"Failed to send DEX trade result: {e}")
            return False
    
    async def send_cex_trade_result(self, trade_result_data: Dict[str, Any]) -> bool:
        """Send CEX trade result notification"""
        if not self.is_available():
            return False
            
        try:
            status = trade_result_data.get('status', 'unknown').capitalize()
            profit = f"${trade_result_data.get('profit_usd', 0):.2f}" if trade_result_data.get('profit_usd') is not None else "N/A"
            
            text = (
                f"📊 <b>CEX Trade Result</b>\n"
                f"Status: {status}\n"
                f"Message: {trade_result_data.get('message', 'N/A')}\n"
                f"Trade ID: {trade_result_data.get('trade_id', 'N/A')}\n"
                f"Profit: {profit}"
            )
            
            return await self.send_message(text)
            
        except Exception as e:
            logger.error(f"Failed to send CEX trade result: {e}")
            return False
    
    def _get_strategy_emoji(self, strategy_type: str) -> str:
        """Get emoji for strategy type."""
        emoji_map = {
            "cross_arbitrage": "🔄",
            "triangular_arbitrage": "🔺", 
            "flash_loan_arbitrage": "⚡",
            "mempool_arbitrage": "🎯"
        }
        return emoji_map.get(strategy_type, "💱")

    def _get_chain_name(self, chain_id: int) -> str:
        """Get human-readable chain name from chain ID."""
        chain_map = {
            1: "Ethereum",
            11155111: "Ethereum Sepolia",
            56: "BSC",
            97: "BSC Testnet", 
            137: "Polygon",
            80001: "Polygon Mumbai"
        }
        return chain_map.get(chain_id, f"Chain {chain_id}")

    def _get_explorer_url(self, chain_id: int, tx_hash: str) -> str:
        """Get block explorer URL for transaction."""
        explorer_map = {
            1: f"https://etherscan.io/tx/{tx_hash}",
            11155111: f"https://sepolia.etherscan.io/tx/{tx_hash}",
            56: f"https://bscscan.com/tx/{tx_hash}",
            97: f"https://testnet.bscscan.com/tx/{tx_hash}",
            137: f"https://polygonscan.com/tx/{tx_hash}",
            80001: f"https://mumbai.polygonscan.com/tx/{tx_hash}"
        }
        return explorer_map.get(chain_id, f"https://etherscan.io/tx/{tx_hash}")
    
    async def close(self):
        """Close the bot session"""
        if self.bot:
            await self.bot.session.close()
            logger.info("Telegram bot session closed")


# Global instance
telegram_manager = TelegramBotManager()
