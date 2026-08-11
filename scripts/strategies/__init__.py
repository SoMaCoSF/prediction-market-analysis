#!/usr/bin/env python3
"""
Panic fade strategy — buys after >10¢ drops when bid is still >20¢.
Based on TurbineFi backtest: 93/96 profitable on KXBTC15M.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from trading_engine import Event, EventType, Strategy, TradingEngine  # noqa: E402


class PanicFadeStrategy(Strategy):
    DROP_THRESHOLD = 0.10  # 10¢
    MIN_BID = 0.20  # 20¢
    MAX_POSITIONS = 2
    COOLDOWN_SEC = 120

    def __init__(self):
        self.last_prices: dict = {}
        self.last_signal_ts: dict = {}
        self.positions = 0

    async def on_market_tick(self, event: Event, engine: TradingEngine) -> list:
        ticker = event.data.get("ticker")
        if not ticker:
            return []

        last_price = float(event.data.get("last_price_dollars", 0) or 0)
        yes_bid = float(event.data.get("yes_bid_dollars", 0) or 0)

        if last_price <= 0 or yes_bid <= 0:
            return []

        prev_price = self.last_prices.get(ticker, last_price)
        price_drop = prev_price - last_price

        if price_drop >= self.DROP_THRESHOLD and yes_bid >= self.MIN_BID:
            now = time.time()
            if now - self.last_signal_ts.get(ticker, 0) > self.COOLDOWN_SEC:
                if self.positions < self.MAX_POSITIONS:
                    # Create order event
                    self.positions += 1
                    self.last_signal_ts[ticker] = now
                    engine.emit(Event(
                        type=EventType.WHALE_SIGNAL,
                        data={
                            "strategy": self.get_name(),
                            "ticker": ticker,
                            "action": "buy_yes",
                            "price_cents": int(yes_bid * 100),
                            "reason": f"panic_fade: {price_drop*100:.1f}¢ drop"
                        },
                        source=self.get_name()
                    ))

        self.last_prices[ticker] = last_price
        return []

    async def on_trade_fill(self, event: Event, engine: TradingEngine) -> list:
        return []

    async def on_order_update(self, event: Event, engine: TradingEngine) -> list:
        return []

    def get_name(self) -> str:
        return "panic_fade"

class WhaleFollowStrategy(Strategy):
    VOLUME_THRESHOLD = 1000  # $1k
    PRICE_MOVE_THRESHOLD = 0.05  # 5¢
    COOLDOWN_SEC = 60
    MAX_POSITIONS = 2

    def __init__(self):
        self.last_volumes: dict = {}
        self.last_prices: dict = {}
        self.last_signal_ts: dict = {}
        self.positions = 0

    async def on_market_tick(self, event: Event, engine: TradingEngine) -> list:
        ticker = event.data.get("ticker")
        if not ticker:
            return []

        vol = float(event.data.get("volume_24h", 0) or 0)
        last_price = float(event.data.get("last_price_dollars", 0) or 0)

        if vol <= 0 or last_price <= 0:
            return []

        prev_vol = self.last_volumes.get(ticker, 0)
        prev_price = self.last_prices.get(ticker, last_price)

        vol_delta = vol - prev_vol
        price_move = abs(last_price - prev_price)

        now = time.time()
        if vol_delta >= self.VOLUME_THRESHOLD or price_move >= self.PRICE_MOVE_THRESHOLD:
            if now - self.last_signal_ts.get(ticker, 0) > self.COOLDOWN_SEC:
                if self.positions < self.MAX_POSITIONS:
                    sig_type = "VOLUME_WHALE" if vol_delta >= self.VOLUME_THRESHOLD else "PRICE_MOVE"
                    self.positions += 1
                    self.last_signal_ts[ticker] = now
                    engine.emit(Event(
                        type=EventType.WHALE_SIGNAL,
                        data={
                            "strategy": self.get_name(),
                            "ticker": ticker,
                            "signal_type": sig_type,
                            "vol_delta": vol_delta,
                            "price_move_cents": price_move * 100,
                        },
                        source=self.get_name()
                    ))

        self.last_volumes[ticker] = vol
        self.last_prices[ticker] = last_price
        return []

    async def on_trade_fill(self, event: Event, engine: TradingEngine) -> list:
        return []

    async def on_order_update(self, event: Event, engine: TradingEngine) -> list:
        return []

    def get_name(self) -> str:
        return "whale_follow"

class ArbStrategy(Strategy):
    """Intra-market arbitrage — buy both YES+NO when combined < $0.99."""

    def __init__(self):
        self.last_signals: dict = {}
        self.cooldown = 300  # 5 min

    async def on_market_tick(self, event: Event, engine: TradingEngine) -> list:
        ticker = event.data.get("ticker")
        if not ticker:
            return []

        yes_ask = float(event.data.get("yes_ask_dollars", 0) or 0)
        no_ask = float(event.data.get("no_ask_dollars", 0) or 0)

        if yes_ask <= 0 or no_ask <= 0:
            return []

        combined = yes_ask + no_ask
        if combined < 0.99:
            now = time.time()
            if now - self.last_signals.get(ticker, 0) > self.cooldown:
                self.last_signals[ticker] = now
                engine.emit(Event(
                    type=EventType.WHALE_SIGNAL,
                    data={
                        "strategy": self.get_name(),
                        "ticker": ticker,
                        "type": "BUY_BOTH",
                        "yes_ask": yes_ask,
                        "no_ask": no_ask,
                        "combined_cost": combined,
                        "profit": 1.0 - combined,
                    },
                    source=self.get_name()
                ))
        return []

    async def on_trade_fill(self, event: Event, engine: TradingEngine) -> list:
        return []

    async def on_order_update(self, event: Event, engine: TradingEngine) -> list:
        return []

    def get_name(self) -> str:
        return "arb"
