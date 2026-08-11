#!/usr/bin/env python3
"""
airfare_tuesday.py

Kalshi-side strategy assistant for the Tuesday 2-4 AM airfare window.
Inspects live market text for airline-proxy keywords and emits engine
events when a flight-pricing proxy looks attractive. It does not book
flights and does not require a booking-session credential.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from trading_engine import Event, EventType, Strategy  # noqa: E402

AIRLINE_KEYWORDS = [
    "airline", "airlines", "flight", "fare", "jetblue", "delta", "united",
    "southwest", "american", "boeing", "airways", "lufthansa", "ryanair",
    "aer lingus", "air canada", "hawaiian", "alaska", "spirit", "frontier",
]


class AirfareTuesdayStrategy(Strategy):
    NAME = "airfare_tuesday"

    def get_name(self):
        return self.NAME

    def _in_window(self, now=None):
        now = now or datetime.now()
        return now.weekday() == 1 and 2 <= now.hour < 4

    def _looks_airline(self, market):
        text = json.dumps(market).lower()
        ticker = market.get("ticker", "").upper()
        series = market.get("series_ticker", "").upper()
        return any(k in text for k in AIRLINE_KEYWORDS) or series.startswith("KXAIR") or ticker.startswith("KXAIR")

    async def on_market_tick(self, event, engine):
        if not self._in_window():
            return
        market = (event.data or {}).get("market") or event.data or {}
        if not self._looks_airline(market):
            return
        price = market.get("last_price_dollars") or market.get("yes_bid_dollars") or market.get("yes_ask_dollars")
        try:
            price = float(price)
        except (TypeError, ValueError):
            return
        if price <= 0 or price > 0.99:
            return
        engine.emit(Event(
            type=EventType.WHALE_SIGNAL,
            source="airfare_tuesday",
            data={
                "ticker": market.get("ticker"),
                "side": "yes",
                "price": price,
                "session_hint": "tue_2_4am_airfare",
            },
        ))
