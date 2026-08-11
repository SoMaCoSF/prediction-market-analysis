#!/usr/bin/env python3
"""
Whale follow strategy — follows large volume spikes and price moves.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from trading_engine import Event, EventType, Strategy, TradingEngine  # noqa: E402


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
