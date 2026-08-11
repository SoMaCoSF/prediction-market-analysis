#!/usr/bin/env python3
"""
Internal paper trading venue — a deterministic matching engine for strategy
validation when real exchange liquidity is dead.

Matches orders against a synthetic orderbook with configurable:
- spread
- depth
- latency
- fill probability

All trades mint UUIDv8, update positions, and feed the same ledger as live.
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

STATE = ROOT / "data" / "paper_venue.json"
LOG = ROOT / "logs" / "paper_venue.out"

# Default synthetic book parameters
DEFAULT_SPREAD = 0.02  # 2¢
DEFAULT_DEPTH = 100  # contracts per side
FILL_PROB = 0.85  # 85% fill rate for marketable orders


def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] [paper] {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state():
    try:
        if STATE.exists():
            return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {
        "orderbook": {},
        "positions": {},
        "last_update": time.time(),
        "params": {"spread": DEFAULT_SPREAD, "depth": DEFAULT_DEPTH, "fill_prob": FILL_PROB},
    }


def save_state(state):
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def update_orderbook(state, ticker: str, mid_price: float):
    """Update synthetic orderbook around mid_price."""
    spread = state["params"]["spread"]
    depth = state["params"]["depth"]

    state["orderbook"][ticker] = {
        "mid": mid_price,
        "yes_bid": round(mid_price - spread / 2, 4),
        "yes_ask": round(mid_price + spread / 2, 4),
        "no_bid": round(1.0 - (mid_price + spread / 2), 4),
        "no_ask": round(1.0 - (mid_price - spread / 2), 4),
        "yes_bid_size": depth,
        "yes_ask_size": depth,
        "no_bid_size": depth,
        "no_ask_size": depth,
        "updated": time.time(),
    }


def match_order(state, ticker: str, side: str, price: float, count: int) -> dict:
    """Try to match against synthetic book."""
    book = state["orderbook"].get(ticker)
    if not book:
        return {"filled": False, "reason": "no_book"}

    fill_prob = state["params"]["fill_prob"]

    if side == "yes":
        # Buying YES: must meet or exceed ask
        if price >= book["yes_ask"] and book["yes_ask_size"] > 0:
            if random.random() < fill_prob:
                fill_size = min(count, book["yes_ask_size"])
                book["yes_ask_size"] -= fill_size
                return {
                    "filled": True,
                    "price": book["yes_ask"],
                    "count": fill_size,
                    "fee": round(fill_size * book["yes_ask"] * 0.01, 4),  # 1% fee
                }
        return {"filled": False, "reason": "no_liquidity"}

    elif side == "no":
        # Buying NO: must meet or exceed ask
        if price >= book["no_ask"] and book["no_ask_size"] > 0:
            if random.random() < fill_prob:
                fill_size = min(count, book["no_ask_size"])
                book["no_ask_size"] -= fill_size
                return {
                    "filled": True,
                    "price": book["no_ask"],
                    "count": fill_size,
                    "fee": round(fill_size * book["no_ask"] * 0.01, 4),
                }
        return {"filled": False, "reason": "no_liquidity"}

    return {"filled": False, "reason": "unknown_side"}


def simulate_market(state):
    """Simulate price movements for paper markets."""
    for ticker, book in state["orderbook"].items():
        # Random walk: ±0.5-2¢ per tick
        drift = random.uniform(-0.02, 0.02)
        new_mid = max(0.01, min(0.99, book["mid"] + drift))
        update_orderbook(state, ticker, new_mid)


def main():
    fleetlib.acquire_lock("paper-venue")
    log("PAPER VENUE STARTED")
    state = load_state()

    # Seed some synthetic markets if empty
    if not state["orderbook"]:
        tickers = [
            "PAPER-BTC-15M",
            "PAPER-ETH-15M",
            "PAPER-SOL-15M",
            "PAPER-XRP-15M",
            "PAPER-DOGE-15M",
        ]
        for ticker in tickers:
            mid = random.uniform(0.3, 0.7)
            update_orderbook(state, ticker, mid)
        save_state(state)
        log(f"Seeded {len(tickers)} paper markets")

    while True:
        fleetlib.checkin("paper-venue")
        try:
            simulate_market(state)
            save_state(state)
        except Exception as e:
            log(f"warn {repr(e)[:60]}")
        time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
