#!/usr/bin/env python3
"""Real-time Kalshi orderbook monitor — polls 200 markets, shows live depth, alerts on movement."""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import httpx  # noqa: E402

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
ALERT_FILE = ROOT / "logs" / "orderbook_alert.log"

last_snapshot: dict[str, dict] = {}
alert_count = 0


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def fetch_markets() -> list[dict]:
    try:
        r = httpx.get(f"{KALSHI}/markets", params={"limit": 200, "status": "open"}, timeout=20)
        r.raise_for_status()
        return r.json().get("markets", [])
    except Exception as exc:
        log(f"fetch error: {repr(exc)[:60]}")
        return []


def check_movement(markets: list[dict]) -> list[dict]:
    moved = []
    for m in markets:
        ticker = m.get("ticker", "")
        yb = float(m.get("yes_bid_dollars") or 0)
        ya = float(m.get("yes_ask_dollars") or 0)
        vol = float(m.get("volume_24h_fp") or m.get("volume_24h") or 0)
        spread_cents = round((ya - yb) * 100, 2) if ya > yb else 0

        prev = last_snapshot.get(ticker, {})
        prev_yb = prev.get("yes_bid_dollars", 0)
        prev_vol = prev.get("volume_24h", 0)

        price_moved = prev_yb > 0 and abs(yb - prev_yb) > 0.0001
        vol_moved = prev_vol > 0 and vol > prev_vol
        new_depth = yb > 0 and ya > 0 and vol > 0

        last_snapshot[ticker] = {
            "yes_bid_dollars": yb,
            "yes_ask_dollars": ya,
            "volume_24h": vol,
        }

        if price_moved or vol_moved or new_depth:
            moved.append({
                "ticker": ticker,
                "yes_bid_c": round(yb * 100, 2),
                "yes_ask_c": round(ya * 100, 2),
                "spread_c": spread_cents,
                "volume_24h": vol,
                "price_moved": price_moved,
                "vol_moved": vol_moved,
                "new_depth": new_depth,
            })
    return moved


def print_header():
    print("\n" + "=" * 100, flush=True)
    print(f"{'TICKER':<45} {'BID':>6} {'ASK':>6} {'SPREAD':>7} {'VOL 24H':>12} {'STATUS':<20}", flush=True)
    print("=" * 100, flush=True)


def print_markets(markets: list[dict]):
    if not markets:
        log("no markets returned")
        return
    print_header()
    actionable = []
    for m in markets:
        ticker = m.get("ticker", "")
        yb = float(m.get("yes_bid_dollars") or 0)
        ya = float(m.get("yes_ask_dollars") or 0)
        vol = float(m.get("volume_24h_fp") or m.get("volume_24h") or 0)
        spread_cents = round((ya - yb) * 100, 2) if ya > yb else 0
        yb_c = round(yb * 100, 2)
        ya_c = round(ya * 100, 2)

        if yb > 0 and ya > 0 and vol > 0:
            status = f"DEPTH {vol:,.0f}"
            actionable.append(m)
        elif yb > 0 or ya > 0:
            status = "ONE-SIDED"
        else:
            status = "EMPTY"

        print(f"{ticker:<45} {yb_c:>6.2f} {ya_c:>6.2f} {spread_cents:>7.2f} {vol:>12,.0f} {status:<20}", flush=True)

    print(f"\nMarkets with real depth: {len(actionable)} / {len(markets)}", flush=True)
    return actionable


def main():
    global alert_count
    log("orderbook monitor starting — polling 200 markets every 10s")
    print_header()

    while True:
        markets = fetch_markets()
        if not markets:
            time.sleep(10)
            continue

        moved = check_movement(markets)
        print_markets(markets)

        if moved:
            alert_count += len(moved)
            log(f"*** {len(moved)} BOOK(S) MOVED ***")
            for item in moved:
                flags = []
                if item["new_depth"]:
                    flags.append("NEW DEPTH")
                if item["price_moved"]:
                    flags.append("PRICE MOVE")
                if item["vol_moved"]:
                    flags.append("VOL MOVE")
                flag_str = " | ".join(flags)
                log(f"  {item['ticker']:<45} bid={item['yes_bid_c']:>6.2f} ask={item['yes_ask_c']:>6.2f} "
                    f"spread={item['spread_c']:>5.2f}c vol={item['volume_24h']:>10,.0f} [{flag_str}]")

            try:
                ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
                with ALERT_FILE.open("a") as f:
                    for item in moved:
                        flags = []
                        if item["new_depth"]:
                            flags.append("NEW_DEPTH")
                        if item["price_moved"]:
                            flags.append("PRICE_MOVE")
                        if item["vol_moved"]:
                            flags.append("VOL_MOVE")
                        f.write(f"{datetime.now().isoformat()} {item['ticker']} bid={item['yes_bid_c']} "
                                f"ask={item['yes_ask_c']} spread={item['spread_c']}c vol={item['volume_24h']} "
                                f"flags={','.join(flags)}\n")
            except Exception:
                pass

        now = datetime.now()
        wait = max(10, (60 - now.second) % 60)
        log(f"next scan in {wait}s | total alerts: {alert_count}")
        time.sleep(wait)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("stopped")
