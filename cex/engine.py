import asyncio
import ccxt.pro as ccxt
import json
import os
import logging
import time
from datetime import datetime
from decimal import Decimal, getcontext
from typing import Dict, List, Optional
import aiohttp
from .models import Opportunity, asdict

# Set Decimal precision high for financial math
getcontext().prec = 60

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('arbitrage.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Small helper: aiohttp session factory with timeout and retry-like behavior
async def fetch_json_with_timeout(url: str, method: str = "GET", json_payload=None, headers=None, timeout=8):
    try:
        async with aiohttp.ClientSession() as session:
            if method.upper() == "GET":
                async with session.get(url, headers=headers, timeout=timeout) as resp:
                    text = await resp.text()
                    return resp.status, await resp.json()
            elif method.upper() == "POST":
                async with session.post(url, headers=headers, json=json_payload, timeout=timeout) as resp:
                    text = await resp.text()
                    try:
                        return resp.status, await resp.json()
                    except Exception:
                        return resp.status, {"raw": text}
    except asyncio.TimeoutError:
        logger.error(f"[HTTP] Timeout when calling {url}")
        return None, None
    except Exception as e:
        logger.error(f"[HTTP] Error when calling {url}: {e}")
        return None, None


class Engine:
    """Core Arbitrage Engine handling exchange initialization, balance updates, and opportunity logging."""
    account_balances: Dict[str, Dict[str, float]] = {}  # {exchange: {asset: balance}}
    slippage_tolerance = Decimal('0.005')  # 0.5% default tolerance

    def __init__(self, base44_api_url: str, app_token: str, notifier=None):
        self.base44_api_url = base44_api_url
        self.app_token = app_token
        self.notifier = notifier

        self.headers = {
            'api_key': self.app_token,
            'Content-Type': 'application/json'
        }

        self.exchanges: Dict[str, ccxt.Exchange] = {}
        # Minimum profit threshold (%) to consider an opportunity valid (double-checked with config)
        self.min_profit_threshold = float(os.getenv('MIN_PROFIT_THRESHOLD', '0.3'))
        self.reconnect_delay = int(os.getenv('RECONNECT_DELAY', '30'))
        self.seen_opportunities = set()  # Cache of signatures
        self.cache_ttl = 60  # seconds
        self.loaded_config = None
        self.seen_timestamps = {}
        self.running = False

        # lock for critical execution sections (optional usage)
        self._internal_lock = asyncio.Lock()

    # -----------------------------
    # Base44 / config helpers
    # -----------------------------
    async def fetch_exchanges(self):
        """Load exchange configurations from base44 database"""
        if not self.base44_api_url:
            logger.warning("No BASE44_API_URL configured.")
            return None

        url = f"{self.base44_api_url}/entities/Exchange"
        status, payload = await fetch_json_with_timeout(url, method="GET", headers=self.headers, timeout=8)
        if status in (200, 201) and payload:
            return payload
        logger.error(f"Failed to fetch exchanges from Base44 (status={status})")
        return None

    async def watch_base44_config(self):
        while True:
            try:
                if not self.loaded_config:
                    self.loaded_config = await self.fetch_exchanges()

                load_config = await self.fetch_exchanges()
                if not load_config:
                    await asyncio.sleep(self.reconnect_delay)
                    continue

                if load_config != self.loaded_config:
                    logger.info("Detect configuration update. Re-initializing exchanges...")
                    await self.stop()
                    await asyncio.sleep(2)
                    await self.initialize_exchanges(load_config)
                await asyncio.sleep(1800)
            except Exception as e:
                logger.error(f"Error in watch_base44_config: {e}")
                await asyncio.sleep(self.reconnect_delay)

    # -----------------------------
    # Exchange initialization
    # -----------------------------
    async def initialize_exchanges(self, config=None):
        """Initialize exchanges with retry-per-exchange and safe close on failure."""
        try:
            exchange_configs = await self.fetch_exchanges() if not config else config
            if not exchange_configs:
                logger.warning("No exchange configurations available to initialize.")
                return

            for cfg in exchange_configs:
                try:
                    if not cfg.get('is_active', False):
                        continue

                    exchange_name = cfg.get('name', '').lower()
                    ccxt_name = self._get_ccxt_name(exchange_name)

                    if not hasattr(ccxt, ccxt_name):
                        logger.warning(f"CCXT does not support {ccxt_name}")
                        continue

                    exchange_class = getattr(ccxt, ccxt_name)
                    exchange = exchange_class({
                        'apiKey': cfg.get('api_key', ''),
                        'secret': cfg.get('api_secret', ''),
                        'options': {'defaultType': 'spot'},
                        'enableRateLimit': True,
                        'timeout': 30000,
                        'adjustForTimeDifference': True
                    })

                    # Attempt to load markets with per-exchange try/catch
                    try:
                        await asyncio.wait_for(exchange.load_markets(), timeout=30.0)
                        self.exchanges[exchange_name] = exchange
                        logger.info(f"Successfully initialized {exchange_name}")
                    except asyncio.TimeoutError:
                        logger.error(f"Timeout initializing {exchange_name}")
                        try:
                            await exchange.close()
                        except Exception:
                            pass
                    except Exception as e:
                        logger.error(f"Failed to initialize {exchange_name}: {e}")
                        try:
                            await exchange.close()
                        except Exception:
                            pass

                except Exception as e:
                    logger.error(f"Unhandled error while initializing exchange config: {e}")

            self.loaded_config = exchange_configs
        except Exception as e:
            logger.error(f"Failed to load exchange configurations: {e}")

    def _get_ccxt_name(self, exchange_name: str) -> str:
        """Map exchange names to ccxt identifiers"""
        mapping = {
            'binance': 'binance',
            'coinbase': 'coinbasepro',
            'coinbase pro': 'coinbase',
            'kraken': 'kraken',
            'kucoin': 'kucoin',
            'bybit': 'bybit',
            'mexc': 'mexc',
            'huobi': 'huobi',
            'okx': 'okx',
            'gate.io': 'gate'
        }
        return mapping.get(exchange_name.lower(), exchange_name.lower())

    # -----------------------------
    # Slippage estimation
    # -----------------------------
    async def calc_slippage(self, exchange, symbol: str, side: str, qty: Decimal) -> Optional[Decimal]:
        """
        Estimates slippage for a market order on the given exchange and symbol.
        qty: for BUY -> quote amount (e.g., USD); for SELL -> base amount
        Returns slippage fraction (Decimal) or None if insufficient liquidity
        """
        try:
            orderbook = await exchange.fetch_order_book(symbol)
            if not orderbook or not orderbook.get('bids') or not orderbook.get('asks'):
                return None

            side = side.upper()
            levels = orderbook['asks'] if side == 'BUY' else orderbook['bids']
            filled_base = Decimal('0')
            spent_quote = Decimal('0')

            if side == 'BUY':
                remaining_quote = qty
                for price, amount in levels:
                    price_d = Decimal(str(price))
                    amount_d = Decimal(str(amount))
                    level_quote = price_d * amount_d
                    if remaining_quote <= level_quote:
                        take_quote = remaining_quote
                        take_base = take_quote / price_d
                    else:
                        take_quote = level_quote
                        take_base = amount_d

                    filled_base += take_base
                    spent_quote += take_quote
                    remaining_quote -= take_quote

                    if remaining_quote <= 0:
                        break

                if remaining_quote > 0:
                    return None

                vwap = spent_quote / filled_base
                best_price = Decimal(str(orderbook['asks'][0][0]))
                if best_price == 0:
                    return None
                slippage = (vwap - best_price) / best_price

            else:  # SELL
                remaining_base = qty
                for price, amount in levels:
                    price_d = Decimal(str(price))
                    amount_d = Decimal(str(amount))
                    take_base = min(amount_d, remaining_base)
                    filled_base += take_base
                    spent_quote += take_base * price_d
                    remaining_base -= take_base
                    if remaining_base <= 0:
                        break

                if remaining_base > 0:
                    return None

                vwap = spent_quote / filled_base
                best_price = Decimal(str(orderbook['bids'][0][0]))
                if best_price == 0:
                    return None
                slippage = (best_price - vwap) / best_price

            return max(slippage, Decimal('0'))
        except Exception as e:
            logger.error(f"[SLIPPAGE] Error estimating slippage for {symbol} on {getattr(exchange,'id',str(exchange))}: {e}")
            return None

    def _slippage_ok(self, slip: Optional[Decimal]) -> bool:
        if slip is None:
            return False
        try:
            return slip <= self.slippage_tolerance
        except Exception:
            return False

    # -----------------------------
    # Persistence / logging
    # -----------------------------
    async def _log_trade_to_base44(self, entity_data: dict) -> Optional[str]:
        """Logs a completed or pending trade to the 'Trade' entity."""
        try:
            url = f"{self.base44_api_url}/entities/Trade"
            status, payload = await fetch_json_with_timeout(url, method="POST", json_payload=entity_data, headers=self.headers, timeout=8)
            if status in (200, 201) and payload:
                logger.info(f"Successfully logged trade to base44. ID: {payload.get('id')}")
                return payload.get('id')
            else:
                logger.error(f"Failed to log trade. Status: {status}, payload: {payload}")
                return None
        except Exception as e:
            logger.error(f"Exception while logging trade: {e}")
            return None

    async def save_opportunity(self, op: Opportunity, entity_name: str):
        """Saves an opportunity to the base44 database with duplicate debounce and TTL."""
        try:
            # Build unique signature (include timestamp bucket to reduce collisions)
            now = time.time()
            if entity_name == 'ArbitrageOpportunity':
                signature = f"{op.trading_pair}-{op.buy_exchange}-{op.sell_exchange}-{round(op.profit_percentage, 2)}"
            elif entity_name == 'TriangularOpportunity':
                signature = f"{op.exchange}-{'->'.join(op.trading_path or [])}-{round(op.profit_percentage, 2)}"
            else:
                signature = f"{op.detected_at}"

            if signature in self.seen_opportunities:
                return

            self.seen_opportunities.add(signature)
            self.seen_timestamps[signature] = now
            self._cleanup_seen_cache(now)

            url = f"{self.base44_api_url}/entities/{entity_name}"
            status, payload = await fetch_json_with_timeout(url, method="POST", json_payload=asdict(op), headers=self.headers, timeout=8)
            if status in (200, 201):
                logger.info(f"Saved {entity_name} opportunity: {payload.get('id')}")
                if self.notifier:
                    # best-effort notify (do not block)
                    try:
                        await self.notifier.send_opportunity_alert(op, payload.get('id'))
                    except Exception as e:
                        logger.error(f"Notifier send failed: {e}")
            else:
                logger.error(f"Failed to save {entity_name}: status={status}, payload={payload}")
        except Exception as e:
            logger.error(f"Exception saving {entity_name}: {e}")

    # -----------------------------
    # Balance updater
    # -----------------------------
    async def update_account_balances_periodically(self):
        """Periodically fetches and updates balances for all exchanges with retries."""
        # wait a bit before first fetch
        await asyncio.sleep(5)

        while self.running:
            logger.info("Updating account balances...")
            all_balances = {}
            for name, exchange in list(self.exchanges.items()):
                tries = 0
                balance = {}
                while tries < 3:
                    try:
                        resp = await exchange.fetch_balance()
                        # Filter total balances
                        balance = {
                            asset: data for asset, data in resp.get('total', {}).items() if data and data > 0
                        }
                        break
                    except Exception as e:
                        tries += 1
                        logger.warning(f"Failed to fetch balance for {name} (attempt {tries}): {e}")
                        await asyncio.sleep(1 + tries * 2)
                if balance:
                    all_balances[name] = balance
                else:
                    logger.error(f"Unable to fetch balances for {name} after retries.")
            # atomic replace
            self.account_balances.clear()
            self.account_balances.update(all_balances)
            logger.info("Account balances updated successfully.")
            await asyncio.sleep(300)  # update every 5 minutes

    # -----------------------------
    # Helpers
    # -----------------------------
    def _cleanup_seen_cache(self, now):
        expired = [sig for sig, ts in self.seen_timestamps.items() if now - ts > self.cache_ttl]
        for sig in expired:
            self.seen_opportunities.discard(sig)
            self.seen_timestamps.pop(sig, None)

    async def reconnect(self, exchange, sleep=None):
        await asyncio.sleep(sleep or self.reconnect_delay)
        try:
            await exchange.close()
        except Exception:
            pass

    async def stop(self):
        """Stop the arbitrage engine and cleanup connections"""
        logger.info("Stopping Arbitrage Engine...")
        self.running = False
        for name, exchange in list(self.exchanges.items()):
            try:
                if hasattr(exchange, 'close'):
                    await exchange.close()
                logger.info(f"Closed {name} connection")
            except Exception as e:
                logger.error(f"Error closing {name}: {e}")


# instantiate engine with env vars (safe: no secrets printed)
engine = Engine(base44_api_url=os.getenv('BASE44_API_URL'), app_token=os.getenv('BASE44_APP_TOKEN'))
