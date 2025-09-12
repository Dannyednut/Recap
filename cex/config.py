import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Base44 Configuration
    BASE44_API_URL = os.getenv("BASE44_API_URL", "")
    BASE44_APP_TOKEN = os.getenv("BASE44_APP_TOKEN", "")

    # Trading Configuration
    SYMBOLS = os.getenv("SYMBOLS", "FIL/USDT,QTUM/USDT,DOT/USDT,XRP/USDT,ADA/USDT").split(",")
    MIN_PROFIT_THRESHOLD = float(os.getenv("MIN_PROFIT_THRESHOLD", "0.3"))
    MAX_TRADE_AMOUNT = float(os.getenv("MAX_TRADE_AMOUNT", "1000.0"))

    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    TELEGRAM_API_URL = os.getenv("TELEGRAM_API_URL", "https://api.telegram.org/bot") + TELEGRAM_BOT_TOKEN
    TELEGRAM_ALERTS_ENABLED = os.getenv("TELEGRAM_ALERTS_ENABLED", "True") == "True"
    TELEGRAM_ALERT_THRESHOLD = float(os.getenv("TELEGRAM_ALERT_THRESHOLD", "0.5"))
    TELEGRAM_ALERT_COOLDOWN = int("300")

    # WebSocket Configuration
    ORDERBOOK_LIMIT = int(os.getenv("ORDERBOOK_LIMIT", "1"))
    RECONNECT_DELAY = int(os.getenv("RECONNECT_DELAY", "30"))

    # Quart / Flask Configuration
    FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
    FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
    EXECUTE_URL = os.getenv("EXECUTE_URL", "https://arbitragewise-production.up.railway.app/execute")

    # Logging Configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def validate(cls):
        errors = []
        if not cls.BASE44_API_URL:
            errors.append("BASE44_API_URL not set")
        if not cls.BASE44_APP_TOKEN:
            errors.append("BASE44_APP_TOKEN not set")
        if cls.TELEGRAM_ALERTS_ENABLED and (not cls.TELEGRAM_BOT_TOKEN or not cls.TELEGRAM_CHAT_ID):
            errors.append("Telegram enabled but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        if errors:
            raise RuntimeError("Config validation errors: " + "; ".join(errors))

# perform a runtime validation when module is imported
try:
    Config.validate()
except Exception as e:
    # do NOT crash automatically in dev. Log error for operator to fix.
    # In production you may want to raise to stop the app
    print(f"[CONFIG] Warning: {e}")
