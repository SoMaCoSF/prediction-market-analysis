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
