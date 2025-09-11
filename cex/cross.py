import asyncio
import traceback
import time

from typing import List, Dict
from decimal import Decimal, getcontext
from datetime import datetime

from .config import Config
from .engine import Engine, logger
from .models import TradeResult, Opportunity

getcontext().prec = 60


class CrossExchange(Engine):

    def __init__(self, engine: Engine, config: Config):
        # composition: we use engine instance passed in (don't re-initialize)
        self.engine = engine
        self.price_cache = {}
        self.config = config
        self.reconnect_delay = int(config.RECONNECT_DELAY)
        # Use existing thresholds
        self.min_profit_threshold = float(config.MIN_PROFIT_THRESHOLD)
        # If desired, you can keep a local lock (but the orchestrator already locks execute)
        self._execution_lock = asyncio.Lock()

    # -----------------------------
    # Price streams and detection
    # -----------------------------
    async def start_price_streams(self):
        """Initializes and manages all WebSocket price stream tasks."""
        logger.info("Starting cross-exchange price streams...")
        tasks = []

        for exchange_name, exchange in self.engine.exchanges.items():
            for symbol in self.config.SYMBOLS:
                task = asyncio.create_task(self.stream_manager(exchange_name, exchange, symbol))
                tasks.append(task)

        # Start the separate task for continuously detecting opportunities
        tasks.append(asyncio.create_task(self.continuous_opportunity_detection()))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stream_manager(self, exchange_name: str, exchange, symbol: str):
        """Manages the lifecycle of a single WebSocket stream with automatic reconnection."""
        while self.engine.running:
            try:
                logger.info(f"[{exchange_name}] Subscribing to {symbol}...")
                await self.stream_orderbook(exchange_name, exchange, symbol)
            except Exception as e:
                logger.error(f"[{exchange_name}] Unhandled exception in stream for {symbol}: {e}. Reconnecting in {self.reconnect_delay}s.")
                await asyncio.sleep(self.reconnect_delay)

    async def stream_orderbook(self, exchange_name: str, exchange, symbol: str):
        """The core loop that watches for order book updates from a single stream."""
        reconnect_attempts = 0
        max_reconnect_delay = 300

        while self.engine.running:
            try:
                orderbook = await exchange.watch_order_book(symbol)
                if exchange_name not in self.price_cache:
                    self.price_cache[exchange_name] = {}

                if orderbook and orderbook.get('bids') and orderbook.get('asks'):
                    self.price_cache[exchange_name][symbol] = {
                        'bid': orderbook['bids'][0][0],
                        'ask': orderbook['asks'][0][0],
                        'timestamp': orderbook.get('timestamp', int(time.time() * 1000))
                    }
                    logger.debug(f"Price Update: {exchange_name} {symbol} | Bid: {self.price_cache[exchange_name][symbol]['bid']}, Ask: {self.price_cache[exchange_name][symbol]['ask']}")
                    reconnect_attempts = 0
                else:
                    logger.warning(f"[{exchange_name}] Received invalid order book for {symbol}")

            except Exception as e:
                logger.warning(f"[{exchange_name}] Error in symbol watcher for {symbol}: {e}")
                # Ensure the connection is closed before a new attempt
                try:
                    if hasattr(exchange, 'close'):
                        await exchange.close()
                except Exception:
                    pass

                delay = min(self.reconnect_delay * (2 ** reconnect_attempts), max_reconnect_delay)
                logger.info(f"[{exchange_name}] Reconnecting in {delay} seconds...")
                await asyncio.sleep(delay)
                reconnect_attempts += 1

    async def continuous_opportunity_detection(self):
        """Continuously analyzes the in-memory price cache for arbitrage opportunities."""
        while self.engine.running:
            try:
                for symbol in self.config.SYMBOLS:
                    opportunities = self.analyze_symbol_opportunities(symbol)
                    for opp in opportunities:
                        # Add expiry guard: skip stale opps older than X seconds
                        now_ts = datetime.utcnow().timestamp()
                        # opp.detected_at is ISO string - try convert
                        try:
                            opp_ts = datetime.fromisoformat(opp.detected_at).timestamp()
                        except Exception:
                            opp_ts = now_ts
                        if now_ts - opp_ts > 10:  # 10 seconds max age
                            logger.debug("Skipping stale opportunity")
                            continue

                        # Profit check against engine threshold and configured minimum
                        if opp.profit_percentage < max(self.engine.min_profit_threshold, self.min_profit_threshold):
                            logger.debug("Skipping low-profit opportunity")
                            continue

                        logger.info(f"Cross-Exchange Opportunity: {opp.trading_pair} | Profit: {opp.profit_percentage:.3f}%")
                        await self.engine.save_opportunity(opp, 'ArbitrageOpportunity')

                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Error in continuous opportunity detection loop: {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(10)

    # -----------------------------
    # Opportunity discovery
    # -----------------------------
    def analyze_symbol_opportunities(self, symbol: str) -> list:
        prices = []
        for exchange_name, exchange_data in self.price_cache.items():
            if symbol in exchange_data and exchange_data[symbol].get('bid') and exchange_data[symbol].get('ask'):
                prices.append({
                    'exchange': exchange_name,
                    'symbol': symbol,
                    **exchange_data[symbol]
                })

        if len(prices) >= 2:
            return self._find_arbitrage_opportunities(prices)
        return []

    def _find_arbitrage_opportunities(self, price_data: List[Dict]) -> List[Opportunity]:
        """Analyze price data to find arbitrage opportunities. Includes simple fee estimate."""
        opportunities: List[Opportunity] = []
        if len(price_data) < 2:
            return opportunities

        valid_prices = [p for p in price_data if p and p.get('bid') and p.get('ask')]
        if len(valid_prices) < 2:
            return opportunities

        sorted_by_ask = sorted(valid_prices, key=lambda x: x['ask'])
        sorted_by_bid = sorted(valid_prices, key=lambda x: x['bid'], reverse=True)

        best_buy = sorted_by_ask[0]
        best_sell = sorted_by_bid[0]

        if best_buy['exchange'] == best_sell['exchange']:
            return opportunities

        buy_price = Decimal(str(best_buy['ask']))
        sell_price = Decimal(str(best_sell['bid']))

        if sell_price <= buy_price:
            return opportunities

        # Basic fee estimate (taker fees) - can be replaced by real per-exchange fee lookup
        estimated_fee_pct = Decimal('0.002')  # 0.2% per side default
        trade_amount = Decimal(str(1000))  # simulate $1000 trade (configurable)
        quantity = trade_amount / buy_price
        gross_profit = quantity * (sell_price - buy_price)
        fees = trade_amount * estimated_fee_pct * 2  # buy + sell
        net_profit = gross_profit - fees

        profit_percentage = (net_profit / trade_amount) * 100

        if profit_percentage >= Decimal(str(self.engine.min_profit_threshold)):
            opp = Opportunity(
                trading_pair=best_buy['symbol'],
                buy_exchange=best_buy['exchange'],
                sell_exchange=best_sell['exchange'],
                buy_price=float(buy_price),
                sell_price=float(sell_price),
                profit_percentage=float(profit_percentage),
                profit_usd=float(net_profit),
                volume=float(quantity),
                detected_at=datetime.utcnow().isoformat()
            )
            opportunities.append(opp)
        return opportunities

    # -----------------------------
    # Execution: instant vs transfer
    # -----------------------------
    async def _execute_cross_exchange_trade(self, op: dict, req: dict) -> TradeResult:
        strategy = req.get('strategy')
        amount = float(req.get('amount', self.config.MAX_TRADE_AMOUNT))

        if strategy == 'instant':
            return await self._execute_instant_arbitrage(op, amount)
        elif strategy == 'transfer':
            return await self._execute_transfer_arbitrage(op, amount)
        return TradeResult("error", "Unknown cross-exchange strategy")

    async def _execute_instant_arbitrage(self, op: dict, amount_usd: float) -> TradeResult:
        """Attempt to buy on buy_exchange and sell on sell_exchange concurrently.
        If one side fails after the other succeeded a simple hedge attempt is made to reduce exposure.
        """
        buy_ex_name, sell_ex_name = op['buy_exchange'], op['sell_exchange']
        buy_exchange = self.engine.exchanges.get(buy_ex_name)
        sell_exchange = self.engine.exchanges.get(sell_ex_name)
        pair = op['trading_pair']
        base, quote = pair.split('/')

        if not all([buy_exchange, sell_exchange]):
            return TradeResult("error", "One of the exchanges is not initialized.")

        # Pre-check balances
        buy_balance = self.engine.account_balances.get(buy_ex_name, {}).get(quote, 0)
        sell_balance = self.engine.account_balances.get(sell_ex_name, {}).get(base, 0)

        if buy_balance < amount_usd:
            return TradeResult("error", f"Insufficient {quote} on {buy_ex_name}")
        amount_to_trade_base = amount_usd / op['buy_price']
        if sell_balance < amount_to_trade_base:
            logger.info(f"Sell-exchange doesn't have base asset to cover immediate reverse. Proceeding with instant attempting buy+sell.")
            # not necessarily an error; we will attempt to buy then sell

        # Execute both market orders concurrently via ccxt async interface
        try:
            logger.info(f"⚡️ ATTEMPTING INSTANT ARBITRAGE: {pair} | {amount_usd:.2f} {quote}")
            buy_task = buy_exchange.create_market_buy_order(pair, amount_to_trade_base)
            sell_task = sell_exchange.create_market_sell_order(pair, amount_to_trade_base)

            results = await asyncio.gather(buy_task, sell_task, return_exceptions=True)
            buy_order, sell_order = results

            # If both succeeded
            if not isinstance(buy_order, Exception) and not isinstance(sell_order, Exception):
                # compute profit properly
                buy_cost = Decimal(str(buy_order.get('cost', 0)))
                sell_cost = Decimal(str(sell_order.get('cost', 0)))
                buy_fee = Decimal(str((buy_order.get('fee') or {}).get('cost', 0)))
                sell_fee = Decimal(str((sell_order.get('fee') or {}).get('cost', 0)))
                profit = sell_cost - buy_cost - buy_fee - sell_fee
                log = {
                    "opportunity_id": op.get('id'),
                    "trading_pair": pair,
                    "buy_exchange": buy_ex_name,
                    "sell_exchange": sell_ex_name,
                    "buy_price": buy_order.get('average'),
                    "sell_price": sell_order.get('average'),
                    "quantity": buy_order.get('filled'),
                    "profit_usd": float(profit),
                    "status": "completed",
                    "strategy": "instant"
                }
                trade_id = await self.engine._log_trade_to_base44(log)
                return TradeResult("success", "Instant arbitrage executed successfully.", trade_id, float(profit))

            # Partial failure: one side succeeded, the other failed
            logger.error(f"PARTIAL FAILURE: Buy: {buy_order} | Sell: {sell_order}")

            # Basic hedge strategy:
            # - If buy succeeded but sell failed: try to sell bought asset on buy_exchange immediately to reduce exposure.
            # - If sell succeeded but buy failed: try to buy on sell_exchange (unlikely) or transfer logic to cover exposure.
            # We will attempt best-effort hedge and return an error for manual review.

            # Hedge if buy succeeded
            if not isinstance(buy_order, Exception) and isinstance(sell_order, Exception):
                try:
                    bought_qty = Decimal(str(buy_order.get('filled', 0)))
                    # attempt to sell back on buy_exchange (market sell)
                    logger.info("Attempting hedge: selling bought asset back on buy exchange to reduce exposure.")
                    hedge_order = await buy_exchange.create_market_sell_order(pair, float(bought_qty))
                    hedge_filled = Decimal(str(hedge_order.get('filled', 0)))
                    hedge_sell_cost = Decimal(str(hedge_order.get('cost', 0)))
                    buy_cost = Decimal(str(buy_order.get('cost', 0)))
                    net = hedge_sell_cost - buy_cost
                    logger.error(f"Hedge result: sold {hedge_filled} back for net {net}")
                except Exception as hedge_err:
                    logger.error(f"Hedge attempt failed: {hedge_err}")

            # Hedge if sell succeeded but buy failed (very rare)
            if isinstance(buy_order, Exception) and not isinstance(sell_order, Exception):
                # attempt to buy back at market on sell_exchange
                try:
                    sold_qty = Decimal(str(sell_order.get('filled', 0)))
                    logger.info("Attempting hedge: buying back asset on sell exchange to reduce exposure.")
                    hedge_order = await sell_exchange.create_market_buy_order(pair, float(sold_qty))
                    logger.error(f"Hedge buy result: {hedge_order}")
                except Exception as hedge_err:
                    logger.error(f"Hedge attempt failed: {hedge_err}")

            return TradeResult("error", "Partial execution occurred; manual review required.")
        except Exception as e:
            logger.error(f"Error during instant execution: {e}\n{traceback.format_exc()}")
            return TradeResult("error", str(e))

    async def _execute_transfer_arbitrage(self, op: dict, amount_usd: float) -> TradeResult:
        """Transfer arbitrage: buy on exchange A, withdraw, wait deposit on exchange B, then sell."""
        try:
            buy_ex_name, sell_ex_name = op['buy_exchange'], op['sell_exchange']
            buy_exchange = self.engine.exchanges.get(buy_ex_name)
            sell_exchange = self.engine.exchanges.get(sell_ex_name)
            pair = op['trading_pair']
            base, quote = pair.split('/')

            if not all([buy_exchange, sell_exchange]):
                return TradeResult("error", "One of the exchanges is not initialized.")

            quote_balance = self.engine.account_balances.get(buy_ex_name, {}).get(quote, 0)
            if quote_balance < amount_usd:
                return TradeResult("error", f"Insufficient {quote} on {buy_ex_name} (have: {quote_balance})")

            # 1a. Estimate slippage (BUY)
            amount_base_est = Decimal(str(amount_usd)) / Decimal(str(op['buy_price']))
            slip = await self.engine.calc_slippage(buy_exchange, pair, 'BUY', Decimal(str(amount_usd)))
            if not self.engine._slippage_ok(slip):
                return TradeResult("error", f"Buy slippage too high on {buy_ex_name}: {slip:.4%}")

            # 2. Place Market Buy Order (use with_cost variant if available)
            logger.info(f"[TRANSFER ARB] Buying ~{float(amount_base_est):.6f} {base} on {buy_ex_name}")
            buy_order = await buy_exchange.create_market_buy_order_with_cost(pair, float(amount_usd)) if hasattr(buy_exchange, 'create_market_buy_order_with_cost') else await buy_exchange.create_market_buy_order(pair, float(amount_base_est))
            if not buy_order or buy_order.get('status') not in ('closed', 'filled'):
                return TradeResult("error", "Buy order failed or not filled.")

            amount_base = Decimal(str(buy_order.get('filled', amount_base_est)))
            # 3. Determine transfer network
            common_chains = await self.get_common_transfer_chains(base, buy_exchange, sell_exchange)
            if not common_chains:
                return TradeResult("error", f"No common transfer chains for {base} between {buy_ex_name} and {sell_ex_name}")

            best_chain, fee = await self.select_best_transfer_chain(common_chains, buy_exchange, base)
            if not best_chain:
                return TradeResult("error", f"Could not determine best transfer chain for {base}")

            deposit_info = await sell_exchange.fetch_deposit_address(base, {'network': best_chain})
            address = deposit_info.get('address')
            tag_or_memo = deposit_info.get('tag', None)

            # 4. Withdraw from buy exchange
            withdrawal = await buy_exchange.withdraw(code=base, amount=float(amount_base), address=address, tag=tag_or_memo, params={'network': best_chain})
            withdraw_fee = (withdrawal.get('fee') or {}).get('cost', fee)

            # 5. Wait for deposit (poll balances)
            logger.info(f"[TRANSFER ARB] Waiting for deposit of {float(amount_base):.6f} {base} on {sell_ex_name}")
            max_wait = 600
            interval = 10
            waited = 0
            amount_received = Decimal('0')
            while waited < max_wait:
                try:
                    balance = await sell_exchange.fetch_balance()
                    total_base = Decimal(str(balance.get('total', {}).get(base, 0)))
                    if total_base >= (amount_base - Decimal(str(withdraw_fee))) * Decimal('0.98'):
                        amount_received = total_base
                        logger.info(f"[TRANSFER ARB] Deposit received: {amount_received}")
                        break
                except Exception:
                    pass
                await asyncio.sleep(interval)
                waited += interval

            if amount_received == 0:
                return TradeResult("error", "Timeout waiting for deposit on sell exchange.")

            # 6a. Slippage check on sell
            slip = await self.engine.calc_slippage(sell_exchange, pair, 'SELL', amount_received)
            if not self.engine._slippage_ok(slip):
                return TradeResult("error", f"Sell slippage too high on {sell_ex_name}: {slip:.4%}")

            # 6b. Sell
            sell_order = await sell_exchange.create_market_sell_order(pair, float(amount_received))

            # 7. Profit calc
            buy_cost = Decimal(str(buy_order.get('cost', 0)))
            sell_cost = Decimal(str(sell_order.get('cost', 0)))
            buy_fee = Decimal(str((buy_order.get('fee') or {}).get('cost', 0)))
            sell_fee = Decimal(str((sell_order.get('fee') or {}).get('cost', 0)))
            withdraw_fee_dec = Decimal(str(withdraw_fee or 0))
            profit = sell_cost - buy_cost - buy_fee - sell_fee - withdraw_fee_dec

            trade_log = {
                "opportunity_id": op.get('id'),
                "trading_pair": pair,
                "buy_exchange": buy_ex_name,
                "sell_exchange": sell_ex_name,
                "buy_price": buy_order.get('average'),
                "sell_price": sell_order.get('average'),
                "quantity": float(amount_base),
                "profit_usd": float(profit),
                "status": "completed",
                "strategy": "transfer"
            }
            trade_id = await self.engine._log_trade_to_base44(trade_log)
            logger.info(f"[TRANSFER ARB] Transfer arbitrage successful. Profit: ${float(profit):.2f}")
            return TradeResult("success", "Transfer arbitrage executed successfully.", trade_id, float(profit))

        except Exception as e:
            logger.error(f"[TRANSFER ARB] Error: {e}")
            logger.error(traceback.format_exc())
            return TradeResult("error", f"Exception occurred: {str(e)}")

    # -----------------------------
    # Helper chain utilities
    # -----------------------------
    async def get_common_transfer_chains(self, asset: str, buy_exchange, sell_exchange) -> list:
        """Fetch common transfer chains (networks) for an asset between two exchanges."""
        try:
            buy_currencies = await buy_exchange.fetch_currencies()
            sell_currencies = await sell_exchange.fetch_currencies()

            buy_chains = set()
            sell_chains = set()

            for key, info in buy_currencies.items():
                if key.upper() == asset.upper() and isinstance(info, dict) and 'networks' in info:
                    buy_chains.update(info['networks'].keys())

            for key, info in sell_currencies.items():
                if key.upper() == asset.upper() and isinstance(info, dict) and 'networks' in info:
                    sell_chains.update(info['networks'].keys())

            common = buy_chains & sell_chains
            return list(common)
        except Exception as e:
            logger.error(f"[CHAIN MATCHING] Error fetching common chains: {e}")
            return []

    async def select_best_transfer_chain(self, common_chains: list, buy_exchange, asset: str):
        """
        From a list of common chains, select the best one based on lowest withdrawal fee.
        Returns (best_chain, estimated_fee)
        """
        try:
            buy_currencies = await buy_exchange.fetch_currencies()
            best_chain = None
            best_score = float('inf')
            estimated_fee = 0

            for chain in common_chains:
                currency_info = buy_currencies.get(asset.upper())
                network_info = currency_info.get('networks', {}).get(chain)
                if not network_info:
                    continue
                fee = network_info.get('fee', 0)
                # lower fee wins
                if fee < best_score:
                    best_score = fee
                    estimated_fee = fee
                    best_chain = chain

            return best_chain, estimated_fee
        except Exception as e:
            logger.error(f"[CHAIN SCORING] Error selecting best chain: {e}")
            return None, None

    async def _log_pending_transfer(self, op: dict, amount_usd: float) -> TradeResult:
        logger.info(f"Logging 'Transfer & Trade' for opportunity {op.get('id')}")
        log = {
            "opportunity_id": op.get('id'),
            "trading_pair": op.get('trading_pair'),
            "buy_exchange": op.get('buy_exchange'),
            "sell_exchange": op.get('sell_exchange'),
            "buy_price": op.get('buy_price'),
            "sell_price": op.get('sell_price'),
            "quantity": amount_usd / op.get('buy_price', 1),
            "profit_usd": op.get('profit_usd'),
            "status": "pending",
            "strategy": "transfer"
        }
        trade_id = await self.engine._log_trade_to_base44(log)
        if trade_id:
            return TradeResult("success", "Trade logged as 'pending'. Manual transfer required.", trade_id)
        return TradeResult("error", "Failed to log the pending trade.")
