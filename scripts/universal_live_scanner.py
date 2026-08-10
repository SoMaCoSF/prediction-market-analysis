#!/usr/bin/env python3
"""Universal live scanner — trades any market with real fills, no hardcoded tickers."""
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402
from mission_control import KALSHI_HOST, kalshi_keys, kalshi_post_order, kalshi_sign  # noqa: E402

load_dotenv(ROOT / ".env")

MAX_CONTRACTS = 1
CASH_FLOOR = 15.00
POLL = 15


def log(msg: str) -> None:
    print(f"[{datetime.utcnow().isoformat()}Z] {msg}", flush=True)


def get_cash() -> float:
    try:
        kid, kpath = kalshi_keys()
        ts = str(int(time.time() * 1000))
        sig = kalshi_sign("GET", "/portfolio/balance", ts, kpath)
        h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}
        r = httpx.get(f"{KALSHI_HOST}/portfolio/balance", headers=h, timeout=20)
        r.raise_for_status()
        return float(r.json().get("balance_dollars", 0))
    except Exception:
        return 0.0


def scan_markets() -> list:
    """Scan for markets with ANY real price activity."""
    try:
        kid, kpath = kalshi_keys()
        ts = str(int(time.time() * 1000))
        sig = kalshi_sign("GET", "/markets?limit=200&status=open", ts, kpath)
        h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}
        r = httpx.get(f"{KALSHI_HOST}/markets?limit=200&status=open", headers=h, timeout=20)
        markets = r.json().get("markets", [])
        now = time.time()
        candidates = []
        for m in markets:
            ct = m.get("close_time")
            if ct:
                try:
                    ct_ts = time.mktime(time.strptime(ct[:19], "%Y-%m-%dT%H:%M:%S"))
                    if ct_ts <= now + 60:  # <1min remaining
                        continue
                except Exception:
                    continue
            lp = float(m.get("last_price_dollars") or 0)
            yb = float(m.get("yes_bid_dollars") or 0)
            ya = float(m.get("yes_ask_dollars") or 0)
            ybs = float(m.get("yes_bid_size_fp") or 0)
            yas = float(m.get("yes_ask_size_fp") or 0)
            vol = float(m.get("volume_24h", 0))
            # Has any real activity
            if lp > 0 or yb > 0 or ya > 0 or ybs > 0 or yas > 0 or vol > 0:
                candidates.append({
                    "ticker": m.get("ticker"),
                    "close": ct,
                    "lp": lp,
                    "yb": yb,
                    "ya": ya,
                    "ybs": ybs,
                    "yas": yas,
                    "vol": vol,
                })
        return candidates
    except Exception:
        return []


def trade_market(ticker: str, price_cents: float) -> bool:
    """Buy YES at given price using proven wrapper."""
    try:
        status, resp = kalshi_post_order({
            "ticker": ticker,
            "side": "yes",
            "count": MAX_CONTRACTS,
            "yes_price": price_cents,
            "client_order_id": f"live-{int(time.time()*1000)}",
            "type": "limit",
        })
        log(f"ORDER {ticker} @ {price_cents:.2f}c x{MAX_CONTRACTS}: {status} {resp}")
        fill_count = float(resp.get("fill_count", 0))
        return fill_count > 0
    except Exception as e:
        log(f"TRADE ERR {ticker}: {repr(e)[:100]}")
        return False


def main() -> None:
    log("universal_live_scanner starting")
    last_trade = 0
    while True:
        try:
            cash = get_cash()
            log(f"cash=${cash:.2f}")
            if cash < CASH_FLOOR:
                log(f"cash ${cash:.2f} below floor ${CASH_FLOOR:.2f}")
                time.sleep(60)
                continue

            candidates = scan_markets()
            log(f"found {len(candidates)} active markets")
            for c in candidates[:10]:
                lp = c["lp"] * 100
                yb = c["yb"] * 100
                ya = c["ya"] * 100
                log(f"  {c['ticker']}: lp={lp:.2f}c yb={yb:.2f}c ya={ya:.2f}c vol={c['vol']} close={c['close']}")

            # Trade cheapest market with real fills
            for c in candidates:
                if time.time() - last_trade < 10:
                    break
                lp = c["lp"] * 100
                yb = c["yb"] * 100
                ya = c["ya"] * 100

                # Buy if last price or ask is cheap
                price = lp if lp > 0 else ya
                if price <= 0 or price > 15:
                    continue
                if trade_market(c["ticker"], price):
                    last_trade = time.time()
                    break

        except Exception as e:
            log(f"ERR {repr(e)[:200]}")
        time.sleep(POLL)


if __name__ == "__main__":
    main()
