#!/usr/bin/env python3
"""
Paper venue — internal matching engine fed by REAL Kalshi prices.
When exchange liquidity is dead, we paper trade against real mids
to validate strategy performance before live deployment.
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
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = ["KXBTC15M", "KXETH15M", "KXSOL15M", "KXXRP15M", "KXDOGE15M"]
SPREAD = 0.02
DEPTH = 100
FILL_PROB = 0.85


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
        "params": {"spread": SPREAD, "depth": DEPTH, "fill_prob": FILL_PROB},
    }


def save_state(state):
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def fetch_kalshi_mids():
    """Fetch real mid-prices from Kalshi series."""
    import httpx
    from mission_control import kalshi_keys, kalshi_sign

    mids = {}
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))

    for series in SERIES:
        try:
            path = f"/trade-api/v2/markets?limit=1&status=open&series_ticker={series}"
            sig = kalshi_sign("GET", path, ts, kpath)
            headers = {
                "KALSHI-ACCESS-KEY": kid,
                "KALSHI-ACCESS-SIGNATURE": sig,
                "KALSHI-ACCESS-TIMESTAMP": ts,
            }
            r = httpx.get(f"{KALSHI}{path}", headers=headers, timeout=15)
            data = r.json()
            markets = data.get("markets", [])
            if markets:
                m = markets[0]
                yes_bid = float(m.get("yes_bid_dollars", 0) or 0)
                yes_ask = float(m.get("yes_ask_dollars", 0) or 0)
                if yes_bid > 0 and yes_ask > 0:
                    mids[series] = {
                        "mid": (yes_bid + yes_ask) / 2,
                        "yes_bid": yes_bid,
                        "yes_ask": yes_ask,
                        "no_bid": 1.0 - yes_ask,
                        "no_ask": 1.0 - yes_bid,
                    }
        except Exception:
            continue

    return mids


def update_book(state, mids: dict):
    """Update orderbook with real Kalshi prices + synthetic spread."""
    spread = state["params"]["spread"]
    depth = state["params"]["depth"]

    for series, mid_data in mids.items():
        mid = mid_data["mid"]
        state["orderbook"][series] = {
            "mid": mid,
            "yes_bid": round(mid - spread / 2, 4),
            "yes_ask": round(mid + spread / 2, 4),
            "no_bid": round(1.0 - (mid + spread / 2), 4),
            "no_ask": round(1.0 - (mid - spread / 2), 4),
            "yes_bid_size": depth,
            "yes_ask_size": depth,
            "no_bid_size": depth,
            "no_ask_size": depth,
            "updated": time.time(),
            "source": "kalshi",
        }


def match_order(state, series: str, side: str, price: float, count: int) -> dict:
    """Try to match against synthetic book."""
    book = state["orderbook"].get(series)
    if not book:
        return {"filled": False, "reason": "no_book"}

    fill_prob = state["params"]["fill_prob"]

    if side == "yes":
        if price >= book["yes_ask"] and book["yes_ask_size"] > 0:
            if random.random() < fill_prob:
                fill_size = min(count, book["yes_ask_size"])
                book["yes_ask_size"] -= fill_size
                return {
                    "filled": True,
                    "price": book["yes_ask"],
                    "count": fill_size,
                    "fee": round(fill_size * book["yes_ask"] * 0.01, 4),
                }
        return {"filled": False, "reason": "no_liquidity"}

    elif side == "no":
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


def main():
    fleetlib.acquire_lock("paper-venue")
    log("PAPER VENUE STARTED — feeding from real Kalshi mids")
    state = load_state()

    # Seed synthetic books if empty
    if not state["orderbook"]:
        for series in SERIES:
            update_book(state, {series: {"mid": random.uniform(0.3, 0.7)}})
        save_state(state)
        log(f"Seeded {len(SERIES)} paper markets")

    while True:
        fleetlib.checkin("paper-venue")
        try:
            mids = fetch_kalshi_mids()
            if mids:
                update_book(state, mids)
                log(f"Updated {len(mids)} markets from Kalshi")
            save_state(state)
        except Exception as e:
            log(f"warn {repr(e)[:60]}")
        time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
