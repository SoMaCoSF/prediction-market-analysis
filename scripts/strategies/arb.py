#!/usr/bin/env python3
"""
Arbitrage strategy — intra-market arb when YES+NO combined < $0.99.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from trading_engine import Event, EventType, Strategy, TradingEngine  # noqa: E402


class ArbStrategy(Strategy):
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
