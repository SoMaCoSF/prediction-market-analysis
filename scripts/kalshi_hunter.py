#!/usr/bin/env python3
"""Kalshi+++ universal hunter — trades ANY market with volume using mean-reversion.

Scans all open markets (no series filter), applies contrarian signal at price extremes,
and uses IoC exits. Works on sports, politics, crypto, whatever has liquidity.
"""
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402
from mission_control import KALSHI_HOST, kalshi_keys, kalshi_sign  # noqa: E402

load_dotenv(ROOT / ".env")

# ---- risk controls ----
MAX_CONTRACTS_PER_ORDER = 2
MAX_OPEN_POSITIONS = 3
CASH_FLOOR = 15.00
MAX_RISK_PER_TRADE = 0.20  # $3 on $15 cash
SCALP_C = 5
STOP_C = 3
POLL = 60
MIN_TTL = 300  # 5 min minimum life
MIN_VOLUME = 50  # minimum 24h volume to consider

# Mean-reversion thresholds (cents)
REVERSION_THRESHOLD = 15  # YES below 15¢ → buy YES; YES above 85¢ → buy NO
MAX_ENTRY_PRICE = 100 - SCALP_C - 2


def log(msg: str) -> None:
    line = f"[{datetime.utcnow().isoformat()}Z] {msg}"
    print(line, flush=True)


def get_cash() -> float:
    try:
        kid, kpath = kalshi_keys()
        ts = str(int(time.time() * 1000))
        sig = kalshi_sign("GET", "/portfolio/balance", ts, kpath)
        h = {
            "KALSHI-ACCESS-KEY": kid,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "KALSHI-ACCESS-TIMESTAMP": ts,
        }
        r = httpx.get(f"{KALSHI_HOST}/portfolio/balance", headers=h, timeout=20)
        r.raise_for_status()
        d = r.json()
        return float(d.get("balance_dollars", 0))
    except Exception:
        return 0.0


def get_markets() -> dict:
    """Broad scan: ALL open markets, no series filter."""
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("GET", "/markets", ts, kpath)
    h = {
        "KALSHI-ACCESS-KEY": kid,
        "KALSHI-ACCESS-SIGNATURE": sig,
        "KALSHI-ACCESS-TIMESTAMP": ts,
    }
    markets = {}
    try:
        r = httpx.get(
            f"{KALSHI_HOST}/markets",
            params={"limit": 200, "status": "open"},
            headers=h,
            timeout=20,
        )
        r.raise_for_status()
        for m in r.json().get("markets", []):
            ticker = m.get("ticker") or ""
            if not ticker.startswith("KX"):
                continue
            ya = float(m.get("yes_ask_dollars") or 0) * 100
            yb = float(m.get("yes_bid_dollars") or 0) * 100
            vol = float(m.get("volume_24h") or 0)
            close = m.get("close_time")
            if yb > 0 and ya > 0 and 1 <= ya <= MAX_ENTRY_PRICE and vol >= MIN_VOLUME and close:
                try:
                    close_ts = datetime.fromisoformat(close.replace("Z", "+00:00")).timestamp()
                    ttl = close_ts - time.time()
                    if ttl < MIN_TTL:
                        continue
                except Exception:
                    pass
                markets[ticker] = {
                    "yes_ask": ya,
                    "yes_bid": yb,
                    "volume": vol,
                    "close": close,
                }
    except Exception as e:
        log(f"market ERR: {e}")
    return markets


def mean_reversion_signal(m: dict) -> tuple:
    """Return (side, price_cents, confidence) or (None, None, None)."""
    ya = m["yes_ask"]
    vol = m["volume"]

    # YES is cheap → buy YES (contrarian)
    if ya < REVERSION_THRESHOLD:
        return "yes", int(ya), min(vol / 1000.0, 1.0)
    # YES is expensive → buy NO (contrarian)
    if ya > 100 - REVERSION_THRESHOLD:
        no_price = int(100 - ya)
        return "no", no_price, min(vol / 1000.0, 1.0)
    return None, None, None


def place_order(ticker: str, side_v1: str, count: int, price_cents: int, tif: str = "immediate_or_cancel") -> dict:
    kid, kpath = kalshi_keys()
    v2_side = "bid" if side_v1 == "yes" else "ask"
    v2_price = price_cents / 100.0 if side_v1 == "yes" else (100 - price_cents) / 100.0
    body = {
        "ticker": ticker,
        "client_order_id": f"hunt-{int(time.time()*1000)}",
        "side": v2_side,
        "count": f"{count:.2f}",
        "price": f"{v2_price:.4f}",
        "time_in_force": tif,
        "self_trade_prevention_type": "taker_at_cross",
        "post_only": False,
        "cancel_order_on_pause": False,
        "reduce_only": False,
        "subaccount": 0,
        "exchange_index": -1,
    }
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("POST", "/portfolio/events/orders", ts, kpath)
    h = {
        "KALSHI-ACCESS-KEY": kid,
        "KALSHI-ACCESS-SIGNATURE": sig,
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "Content-Type": "application/json",
    }
    r = httpx.post(f"{KALSHI_HOST}/portfolio/events/orders", json=body, headers=h, timeout=20)
    return {"status": r.status_code, "resp": r.json()}


def get_open_positions_count() -> int:
    try:
        kid, kpath = kalshi_keys()
        ts = str(int(time.time() * 1000))
        sig = kalshi_sign("GET", "/portfolio/positions", ts, kpath)
        h = {
            "KALSHI-ACCESS-KEY": kid,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "KALSHI-ACCESS-TIMESTAMP": ts,
        }
        r = httpx.get(f"{KALSHI_HOST}/portfolio/positions", headers=h, timeout=20)
        r.raise_for_status()
        positions = r.json().get("market_positions", [])
        return sum(1 for mp in positions if float(mp.get("position_fp") or 0) != 0)
    except Exception:
        return 0


def process_exits(markets: dict) -> None:
    """Exit any open positions using IoC."""
    try:
        kid, kpath = kalshi_keys()
        ts = str(int(time.time() * 1000))
        sig = kalshi_sign("GET", "/portfolio/positions", ts, kpath)
        h = {
            "KALSHI-ACCESS-KEY": kid,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "KALSHI-ACCESS-TIMESTAMP": ts,
        }
        r = httpx.get(f"{KALSHI_HOST}/portfolio/positions", headers=h, timeout=20)
        r.raise_for_status()
        positions = r.json().get("market_positions", [])

        for mp in positions:
            pos_fp = float(mp.get("position_fp") or 0)
            if pos_fp == 0:
                continue
            ticker = mp.get("ticker")
            if ticker not in markets:
                continue
            m = markets[ticker]
            current = float(m.get("yes_bid") or 0)
            if current <= 0:
                continue
            side = "yes" if pos_fp > 0 else "no"
            entry = float(mp.get("avg_cost") or 0) * 100
            if entry <= 0:
                log(f"EXIT SKIP {ticker}: no entry (avg_cost=0)")
                continue
            qty = int(abs(pos_fp))

            # Timeout exit after 15 min
            held = time.time() - float(mp.get("created_time") or time.time())
            if held > 900:
                log(f"EXIT TIMEOUT {ticker} {side} after {held:.0f}s")
                result = place_order(ticker, "no" if side == "yes" else "yes", qty, int(current))
                log(f"EXIT ORDER {result['status']} {result['resp']}")
                continue

            # YES long: sell at bid if >= entry + SCALP_C
            if side == "yes" and current >= entry + SCALP_C:
                sell_px = int(current)
                log(f"EXIT YES {ticker} @ {sell_px}c (entry {entry:.0f}c +{current-entry:.0f}c)")
                result = place_order(ticker, "no", qty, sell_px, tif="immediate_or_cancel")
                log(f"EXIT ORDER {result['status']} {result['resp']}")
            # NO short: cover when YES drops enough
            elif side == "no" and current <= 100 - entry - SCALP_C:
                cover_px = int(current)
                log(f"EXIT NO {ticker} buy YES @ {cover_px}c (NO entry {entry:.0f}c)")
                result = place_order(ticker, "yes", qty, cover_px, tif="immediate_or_cancel")
                log(f"EXIT ORDER {result['status']} {result['resp']}")
    except Exception as e:
        log(f"exit ERR: {e}")


def main() -> None:
    log("kalshi_hunter+++ starting (universal mean-reversion, all series)")
    while True:
        try:
            cash = get_cash()
            if cash < CASH_FLOOR:
                log(f"cash ${cash:.2f} below floor ${CASH_FLOOR:.2f} — sleeping 60s")
                time.sleep(60)
                continue

            markets = get_markets()
            if not markets:
                log("no liquid markets found, sleeping 60s")
                time.sleep(60)
                continue

            log(f"scan: {len(markets)} liquid markets")

            # Exits first
            process_exits(markets)

            # Entries: mean-reversion on price extremes
            open_count = get_open_positions_count()
            if open_count >= MAX_OPEN_POSITIONS:
                log(f"OPEN POSITION CAP: {open_count}/{MAX_OPEN_POSITIONS} — sleeping 60s")
                time.sleep(60)
                continue

            candidates = []
            for ticker, m in markets.items():
                side, price, confidence = mean_reversion_signal(m)
                if side and price and confidence > 0:
                    candidates.append((confidence, ticker, side, price, m["volume"]))

            if not candidates:
                log("no mean-reversion candidates, sleeping 60s")
                time.sleep(60)
                continue

            candidates.sort(key=lambda x: x[0], reverse=True)
            best_conf, best_ticker, best_side, best_price, best_vol = candidates[0]
            risk = max(cash - CASH_FLOOR, 0)
            count = min(max(int(risk * MAX_RISK_PER_TRADE / 0.01), 1), MAX_CONTRACTS_PER_ORDER)

            log(f"HUNT {best_side.upper()} {best_ticker} @ {best_price}c (vol={best_vol:.0f}, conf={best_conf:.2f}) x{count}")
            result = place_order(best_ticker, best_side, count, best_price)
            log(f"ORDER {result['status']} {result['resp']}")
            if result["status"] == 201 and float(result["resp"].get("fill_count", 0)) > 0:
                actual_price = float(result["resp"].get("average_fill_price", best_price / 100.0)) * 100
                log(f"FILLED {best_side} {best_ticker} @ {actual_price:.0f}c")

        except Exception as e:
            log(f"ERR {repr(e)[:200]}")
        time.sleep(POLL)


if __name__ == "__main__":
    main()
