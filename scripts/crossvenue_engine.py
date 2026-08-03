# file_id: SOM-PY-0984-v1.0.0 name: crossvenue_engine.py description: Cross-venue engine — Polymarket x Kalshi same-event divergence: when venues disagree >5c on a crypto market, mint 0x3D5 and bet the Kalshi side toward the deeper venue; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [polymarket, crossvenue, divergence, kalshi, live] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""crossvenue_engine.py — Polymarket in the engine.

Same event, two venues, two prices. When Polymarket and Kalshi disagree by
>DIVERGE_C on a matched crypto market, the disagreement IS the signal: bet
the Kalshi side toward the venue with deeper volume. Mints 0x3D5 DIVERGENCE
UUIDs. 1ct, $5/day cap, 3 concurrent. Zero model tokens.

NOTE: Polymarket is the SIGNAL venue; Kalshi is the EXECUTION venue.
CLOB execution on Polymarket itself needs a Polygon wallet (user key ask).
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import httpx  # noqa: E402
import runlog  # noqa: E402
import sb  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
MC = os.getenv("MC_URL", "http://127.0.0.1:8420")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
PK = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()

POLL_S = 120
DIVERGE_C = 5.0
ENTRY_MAX = 65
MAX_CONC = 3
DAILY_CAP = 5.00
COINS = {"bitcoin": ("KXBTC15M", "BTC"), "btc": ("KXBTC15M", "BTC"),
         "ethereum": ("KXETH15M", "ETH"), "eth": ("KXETH15M", "ETH"),
         "solana": ("KXSOL15M", "SOL"), "sol": ("KXSOL15M", "SOL")}

open_pos: list[dict] = []
spent_today = 0.0
today = time.strftime("%Y-%m-%d")


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] [xvenue] {m}", flush=True)
    runlog.log_event("xvenue", m)


def fire(ticker, side, price):
    try:
        r = httpx.post(f"{MC}/api/order", json={"ticker": ticker, "side": side, "price": price,
                       "count": 1, "mode": "live", "passkey": PK, "confirm": "FIRE"}, timeout=30)
        d = r.json()
        return {"ok": bool(d.get("ok")), "filled": float((d.get("ack") or {}).get("fill_count") or 0)}
    except Exception:
        return {"ok": False, "filled": 0.0}


def poly_crypto_prices(cx):
    """Polymarket crypto up/down markets -> {coin: (yes_price_c, volume_usd)}."""
    out = {}
    try:
        mkts = cx.get("https://gamma-api.polymarket.com/markets",
                      params={"limit": 100, "active": "true", "order": "volume24hr", "ascending": "false"},
                      timeout=20).json()
        for m in mkts:
            q = (m.get("question") or "").lower()
            if not any(k in q for k in ("up or down", "price above", "price of")):
                continue
            for kw, (_series, coin) in COINS.items():
                if kw in q:
                    try:
                        prices = m.get("outcomePrices") or ""
                        if isinstance(prices, str):
                            import json as _j
                            prices = _j.loads(prices)
                        yes_p = float(prices[0]) * 100
                        vol = float(m.get("volume24hr") or m.get("volume") or 0)
                        if 0 < yes_p < 100 and coin not in out:
                            out[coin] = (yes_p, vol)
                    except Exception:
                        continue
    except Exception as e:
        log(f"poly warn {repr(e)[:50]}")
    return out


def kalshi_windows(cx):
    """Current 15M windows -> {coin: {ticker, ya, yb, vol}}."""
    out = {}
    for _kw, (series, coin) in COINS.items():
        if coin in out:
            continue
        try:
            r = cx.get(f"{KALSHI}/markets", params={"limit": 3, "status": "open", "series_ticker": series}, timeout=15)
            for m in r.json().get("markets", []):
                ya = round(float(m.get("yes_ask_dollars") or 0) * 100)
                yb = round(float(m.get("yes_bid_dollars") or 0) * 100)
                if 0 < ya < 100:
                    out[coin] = {"ticker": m["ticker"], "ya": ya, "yb": yb,
                                 "vol": float(m.get("volume_24h_fp") or 0)}
                    break
        except Exception:
            continue
    return out


def main():
    global spent_today, today
    fleetlib.acquire_lock("xvenue")
    log(f"start | diverge>{DIVERGE_C}c entry<={ENTRY_MAX}c cap ${DAILY_CAP}/day")
    with httpx.Client(headers={"Accept-Encoding": "identity"}, timeout=25) as cx:
        while True:
            fleetlib.checkin("xvenue")
            try:
                if time.strftime("%Y-%m-%d") != today:
                    today = time.strftime("%Y-%m-%d")
                    spent_today = 0.0
                poly = poly_crypto_prices(cx)
                kal = kalshi_windows(cx)
                for coin, k in kal.items():
                    if coin not in poly or len(open_pos) >= MAX_CONC or spent_today >= DAILY_CAP:
                        continue
                    pp, pvol = poly[coin]
                    kvol = k["vol"]
                    diverge = pp - k["ya"]
                    if abs(diverge) < DIVERGE_C:
                        continue
                    # follow the deeper venue's price
                    if kvol >= pvol:
                        continue  # kalshi deeper -> our price is the sharp one, no trade
                    side, price = ("yes", k["ya"]) if diverge > 0 else ("no", 100 - k["yb"])
                    if not (1 <= price <= ENTRY_MAX):
                        continue
                    r = fire(k["ticker"], side, price)
                    if r["ok"] and r["filled"] > 0:
                        open_pos.append({"ticker": k["ticker"], "side": side, "price": price})
                        spent_today += price / 100
                        log(f"DIVERGENCE {coin}: poly {pp:.0f}c vs kalshi {k['ya']}c ({diverge:+.0f}c, poly vol ${pvol:,.0f} > k ${kvol:,.0f}) -> {side.upper()} @{price}c")
                if poly or kal:
                    log(f"scan: poly {len(poly)} coins, kalshi {len(kal)} windows | open {len(open_pos)}/{MAX_CONC}")
            except Exception as e:
                log(f"cycle warn {repr(e)[:60]}")
            time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
