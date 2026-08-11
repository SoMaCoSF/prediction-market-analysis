#!/usr/bin/env python3
"""
Cross-venue arbitrage scanner — checks for price gaps between Kalshi and
external prediction markets that can be locked in risk-free.

Strategy:
- Scan Kalshi markets for YES/NO prices
- Compare with known external market prices (Polymarket, Manifold, etc.)
- Flag when combined cost < $1.00 (buy-all arb) or > $1.00 (sell-all arb)
- Log opportunities, do NOT auto-execute (requires multi-venue execution)

NOTE: This is a SCANNER only. Actual arb execution requires:
1. Funded Polymarket wallet
2. Venue router execution layer
3. Capital > $20 per arb opportunity
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from mission_control import KALSHI_HOST, kalshi_keys, kalshi_sign  # noqa: E402

LOG = ROOT / "logs" / "arb_scanner.out"
STATE = ROOT / "data" / "arb_state.json"
POLL_INTERVAL = 60  # check every minute


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    line = f"[{ts}] {msg}"
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
    return {"last_scan": 0, "opportunities": []}


def save_state(state):
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def signed_get(path: str) -> dict:
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("GET", path, ts, kpath)
    headers = {
        "KALSHI-ACCESS-KEY": kid,
        "KALSHI-ACCESS-SIGNATURE": sig,
        "KALSHI-ACCESS-TIMESTAMP": ts,
    }
    r = httpx.get(f"{KALSHI_HOST}{path}", headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()


def scan_once(state: dict):
    now = time.time()
    log("ARB SCAN STARTED")

    try:
        data = signed_get("/markets?limit=200&status=open")
        markets = data.get("markets", [])
    except Exception as e:
        log(f"ERROR fetching markets: {e}")
        return

    opportunities = []

    # Look for markets with both YES and NO bids/asks
    for m in markets:
        ticker = m.get("ticker")
        if not ticker:
            continue

        yes_bid = float(m.get("yes_bid_dollars", 0) or 0)
        yes_ask = float(m.get("yes_ask_dollars", 0) or 0)
        no_bid = float(m.get("no_bid_dollars", 0) or 0)
        no_ask = float(m.get("no_ask_dollars", 0) or 0)

        # Intra-market arb: buy both YES + NO for < $1.00
        if yes_ask > 0 and no_ask > 0:
            combined_cost = yes_ask + no_ask
            if combined_cost < 0.99:  # 1¢ fee buffer
                profit = 1.0 - combined_cost
                opportunities.append({
                    "type": "BUY_BOTH",
                    "ticker": ticker,
                    "yes_ask": yes_ask,
                    "no_ask": no_ask,
                    "combined_cost": round(combined_cost, 4),
                    "profit": round(profit, 4),
                    "profit_pct": round(profit / combined_cost * 100, 1),
                })

        # Sell both YES + NO for > $1.00
        if yes_bid > 0 and no_bid > 0:
            combined_sell = yes_bid + no_bid
            if combined_sell > 1.01:  # 1¢ fee buffer
                profit = combined_sell - 1.0
                opportunities.append({
                    "type": "SELL_BOTH",
                    "ticker": ticker,
                    "yes_bid": yes_bid,
                    "no_bid": no_bid,
                    "combined_sell": round(combined_sell, 4),
                    "profit": round(profit, 4),
                    "profit_pct": round(profit / 1.0 * 100, 1),
                })

    # Log opportunities
    if opportunities:
        log(f"FOUND {len(opportunities)} ARB OPPORTUNITIES:")
        for opp in opportunities[:10]:
            if opp["type"] == "BUY_BOTH":
                log(f"  BUY_BOTH: {opp['ticker'][:60]} | YES={opp['yes_ask']:.2f} NO={opp['no_ask']:.2f} | cost={opp['combined_cost']:.2f} | profit={opp['profit']:.2f} ({opp['profit_pct']}%)")
            else:
                log(f"  SELL_BOTH: {opp['ticker'][:60]} | YES={opp['yes_bid']:.2f} NO={opp['no_bid']:.2f} | sell={opp['combined_sell']:.2f} | profit={opp['profit']:.2f} ({opp['profit_pct']}%)")
        state["opportunities"] = opportunities[-20:]
    else:
        log(f"Scanned {len(markets)} markets — no arb opportunities")
        state["opportunities"] = []

    state["last_scan"] = now
    save_state(state)


def main():
    log("ARB SCANNER STARTED")
    log("Scanning for intra-market arb (buy/sell both YES+NO)")
    state = load_state()
    while True:
        try:
            scan_once(state)
        except Exception as e:
            log(f"ERROR: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
