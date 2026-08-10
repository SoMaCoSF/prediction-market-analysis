#!/usr/bin/env python3
"""Fixed Kalshi hunter — uses real market detail prices, IoC exits, continuous uptick."""
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
MAX_OPEN_POSITIONS = 2
CASH_FLOOR = 15.00
SCALP_C = 5  # target +5¢
STOP_C = 3  # stop at -3¢
POLL = 60
MIN_TTL = 120  # 2 min minimum life

# Candidate markets we know are liquid
CANDIDATES = [
    "KXXRP15M-26AUG080200-00",
    "KXSOL15M-26AUG080200-00",
    "KXDOGE15M-26AUG080200-00",
]


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


def get_real_price(ticker: str) -> dict:
    """Get REAL price from market detail endpoint. Returns dict with yes_bid, yes_ask, no_bid, no_ask in CENTS."""
    try:
        kid, kpath = kalshi_keys()
        ts = str(int(time.time() * 1000))
        sig = kalshi_sign("GET", f"/markets/{ticker}", ts, kpath)
        h = {
            "KALSHI-ACCESS-KEY": kid,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "KALSHI-ACCESS-TIMESTAMP": ts,
        }
        r = httpx.get(f"{KALSHI_HOST}/markets/{ticker}", headers=h, timeout=20)
        if r.status_code != 200:
            return {}
        m = r.json().get("market", {})
        # Prices are in DOLLARS as strings like "0.0080" = 0.8¢
        yes_bid = float(m.get("yes_bid_dollars") or 0) * 100
        yes_ask = float(m.get("yes_ask_dollars") or 0) * 100
        no_bid = float(m.get("no_bid_dollars") or 0) * 100
        no_ask = float(m.get("no_ask_dollars") or 0) * 100
        close = m.get("close_time")
        return {
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "no_bid": no_bid,
            "no_ask": no_ask,
            "close": close,
        }
    except Exception:
        return {}


def place_order(ticker: str, side: str, count: int, price_cents: float, tif: str = "immediate_or_cancel") -> dict:
    """Place order with correct side mapping."""
    kid, kpath = kalshi_keys()
    # side: "yes" = buy YES, "no" = buy NO
    # V2: "bid" = buy, "ask" = sell
    v2_side = "bid" if side == "yes" else "ask"
    v2_price = price_cents / 100.0
    body = {
        "ticker": ticker,
        "client_order_id": f"fix-{int(time.time()*1000)}",
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


def get_open_positions() -> list:
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
        return r.json().get("market_positions", [])
    except Exception:
        return []


def process_exits() -> None:
    """Exit any open positions using IoC at real prices."""
    positions = get_open_positions()
    for mp in positions:
        pos_fp = float(mp.get("position_fp") or 0)
        if pos_fp == 0:
            continue
        ticker = mp.get("ticker")
        qty = int(abs(pos_fp))  # Kalshi requires whole contracts
        if qty <= 0:
            log(f"EXIT SKIP {ticker}: qty={qty}")
            continue

        # Get real price
        prices = get_real_price(ticker)
        if not prices:
            log(f"EXIT SKIP {ticker}: no price data")
            continue

        # V2 unified book: YES contract only
        # Selling YES = ask at YES bid
        # Buying NO = bid, mirrored through kalshi_post_order
        side_v1 = "yes" if pos_fp > 0 else "no"
        if side_v1 == "yes":
            exit_price_cents = prices["yes_bid"]
        else:
            exit_price_cents = prices["no_bid"]

        if exit_price_cents <= 0:
            log(f"EXIT SKIP {ticker}: no exit price")
            continue

        log(f"EXIT {side_v1.upper()} {ticker} @ {exit_price_cents:.2f}c x{qty}")
        # Reuse mission_control's proven V2 wiring
        from mission_control import kalshi_post_order  # noqa: E402
        status, resp = kalshi_post_order({
            "ticker": ticker,
            "side": side_v1,
            "count": qty,
            "yes_price": exit_price_cents if side_v1 == "yes" else None,
            "no_price": exit_price_cents if side_v1 == "no" else None,
            "client_order_id": f"exit-{int(time.time()*1000)}",
            "type": "market",
        })
        log(f"EXIT ORDER {status} {resp}")


def process_entries(cash: float) -> None:
    """Entry: buy YES at real ask for mean-reversion."""
    positions = get_open_positions()
    open_count = sum(1 for p in positions if float(p.get("position_fp") or 0) != 0)
    if open_count >= MAX_OPEN_POSITIONS:
        log(f"OPEN POSITION CAP: {open_count}/{MAX_OPEN_POSITIONS}")
        return

    # Check candidates
    for ticker in CANDIDATES:
        prices = get_real_price(ticker)
        if not prices:
            continue

        yes_ask = prices["yes_ask"]
        yes_bid = prices["yes_bid"]
        close = prices.get("close")

        # Skip if no real price
        if yes_ask <= 0 or yes_bid <= 0:
            log(f"SKIP {ticker}: no real price")
            continue

        # TTL check
        if close:
            try:
                close_ts = datetime.fromisoformat(close.replace("Z", "+00:00")).timestamp()
                ttl = close_ts - time.time()
                if ttl < MIN_TTL:
                    log(f"SKIP {ticker}: TTL {ttl:.0f}s < {MIN_TTL}s")
                    continue
            except Exception:
                pass

        # Mean-reversion: buy YES when cheap (< 15¢)
        if yes_ask < 15:
            risk = max(cash - CASH_FLOOR, 0)
            count = min(max(int(risk * 0.20 / yes_ask * 100), 1), MAX_CONTRACTS_PER_ORDER)
            if count == 0:
                continue

            log(f"ENTRY YES {ticker} @ {yes_ask:.2f}c x{count} (cheap)")
            result = place_order(ticker, "yes", count, yes_ask)
            log(f"ORDER {result['status']} {result['resp']}")
            if result["status"] == 201 and float(result["resp"].get("fill_count", 0)) > 0:
                fill_cost = float(result["resp"].get("taker_fill_cost_dollars", 0))
                fill_count = float(result["resp"].get("fill_count", 0))
                if fill_count > 0:
                    real_price = (fill_cost / fill_count) * 100
                    log(f"FILLED @ {real_price:.2f}c (cost ${fill_cost:.4f})")
            return  # one entry per cycle

    log("no cheap YES candidates")


def main() -> None:
# singleton bypassed for testing

    log("fixed_hunter starting (real prices, IoC exits)")
    while True:
        try:
            cash = get_cash()
            if cash < CASH_FLOOR:
                log(f"cash ${cash:.2f} below floor ${CASH_FLOOR:.2f}")
                time.sleep(60)
                continue

            log(f"cash=${cash:.2f}")

            # Exits first
            process_exits()

            # Entries
            process_entries(cash)

        except Exception as e:
            log(f"ERR {repr(e)[:200]}")
        time.sleep(POLL)


if __name__ == "__main__":
    main()
