#!/usr/bin/env python3
"""Crypto short optimizer — NO-side drift entries on 15M/1H/4H, +15c exits, direct Kalshi V2."""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402
from mission_control import KALSHI_HOST, kalshi_keys, kalshi_sign, sb_cur  # noqa: E402
from profit_scalp import drift  # noqa: E402

load_dotenv(ROOT / ".env")

SERIES = {
    "KXBTC15M": "BTC/USD",
    "KXETH15M": "ETH/USD",
    "KXSOL15M": "SOL/USD",
    "KXXRP15M": "XRP/USD",
    "KXDOGE15M": "DOGEUSD",
    "KXBTC1H": "BTC/USD",
    "KXETH1H": "ETH/USD",
    "KXBTC4H": "BTC/USD",
    "KXETH4H": "ETH/USD",
    "KXSOL1H": "SOL/USD",
    "KXSOL4H": "SOL/USD",
    "KXBTCEOQ": "BTC/USD",
    "KXETHEOQ": "ETH/USD",
    "KXSOLUSD1H": "SOL/USD",
    "KXETHUSD4H": "ETH/USD",
    "KXSOLUSD4H": "SOL/USD",
}

# ---- risk controls ----
MAX_CONTRACTS_PER_ORDER = 5
MAX_OPEN_POSITIONS = 3
MIN_DRIFT_PCT = -0.8  # negative = downside drift for shorts
CASH_FLOOR = 15.00
MAX_RISK_PER_TRADE = 0.15
SCALP_C = 5
STOP_C = 3
POLL = 60
MIN_TTL = 120

# NO-side minimum: need bid > 2¢ to enter (avoid fee bleed on illiquid shorts)
MIN_NO_BID = 2.0


def log(msg: str) -> None:
    line = f"[{datetime.utcnow().isoformat()}Z] {msg}"
    print(line, flush=True)


def get_markets() -> dict:
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("GET", "/markets", ts, kpath)
    h = {
        "KALSHI-ACCESS-KEY": kid,
        "KALSHI-ACCESS-SIGNATURE": sig,
        "KALSHI-ACCESS-TIMESTAMP": ts,
    }
    markets = {}
    for series in SERIES:
        try:
            r = httpx.get(
                f"{KALSHI_HOST}/markets",
                params={"limit": 3, "status": "open", "series_ticker": series},
                headers=h,
                timeout=20,
            )
            r.raise_for_status()
            for m in r.json().get("markets", []):
                ticker = m.get("ticker")
                ya = float(m.get("yes_ask_dollars") or 0) * 100
                yb = float(m.get("yes_bid_dollars") or 0) * 100
                no_bid = 100 - ya  # what you can sell NO at
                no_ask = 100 - yb  # what you can buy NO at
                close = m.get("close_time")
                if yb > 0 and ya > 0 and 1 <= ya <= 99 and no_bid >= MIN_NO_BID and close:
                    try:
                        close_ts = datetime.fromisoformat(close.replace("Z", "+00:00")).timestamp()
                        ttl = close_ts - time.time()
                        if ttl < MIN_TTL:
                            continue
                    except Exception:
                        pass
                    markets[ticker] = {
                        "series": series,
                        "pair": SERIES[series],
                        "yes_ask": ya,
                        "yes_bid": yb,
                        "no_bid": no_bid,
                        "no_ask": no_ask,
                        "close": close,
                    }
        except Exception as e:
            log(f"market ERR {series}: {e}")
    return markets


def size_position(drift_pct: float, cash: float) -> int:
    risk = max(cash - CASH_FLOOR, 0)
    if risk <= 0:
        return 0
    contracts = int(risk * MAX_RISK_PER_TRADE / 0.01)
    return min(max(contracts, 1), MAX_CONTRACTS_PER_ORDER)


def place_order(ticker: str, side_v1: str, count: int, price_cents: int, tif: str = "good_till_canceled", post_only: bool = False) -> dict:
    kid, kpath = kalshi_keys()
    v2_side = "bid" if side_v1 == "yes" else "ask"
    v2_price = price_cents / 100.0 if side_v1 == "yes" else (100 - price_cents) / 100.0
    body = {
        "ticker": ticker,
        "client_order_id": f"short-{int(time.time()*1000)}",
        "side": v2_side,
        "count": f"{count:.2f}",
        "price": f"{v2_price:.4f}",
        "time_in_force": tif,
        "self_trade_prevention_type": "taker_at_cross",
        "post_only": post_only,
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


def get_cash() -> float:
    try:
        con, cur = sb_cur()
        cur.execute("SELECT v FROM mc_state WHERE k=%s", ("watcher:state",))
        row = cur.fetchone()
        if row:
            d = json.loads(row[0])
            return float(d.get("cash", 0))
        con.close()
    except Exception:
        pass
    return 0.0


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


# Local entry tracking for positions where Kalshi avg_cost=0
LOCAL_ENTRIES = {}


def record_entry(ticker: str, side: str, price_cents: float):
    LOCAL_ENTRIES[ticker] = {"side": side, "entry": price_cents, "ts": time.time()}


def get_local_entry(ticker: str) -> tuple:
    e = LOCAL_ENTRIES.get(ticker)
    if e:
        return e["side"], e["entry"]
    return None, None


def main() -> None:
    log("crypto_short_optimizer starting (NO-side drift, direct Kalshi V2)")
    while True:
        try:
            cash = get_cash()
            if cash < CASH_FLOOR:
                log(f"cash ${cash:.2f} below floor ${CASH_FLOOR:.2f} — sleeping 60s")
                time.sleep(60)
                continue

            markets = get_markets()
            if not markets:
                log("no markets found, sleeping 60s")
                time.sleep(60)
                continue

            # ---- EXITS FIRST ----
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
                    current = float(mp.get("last_price") or 0) * 100
                    if current <= 0:
                        # Fallback to orderbook when no last trade
                        current = float(m.get("yes_bid") or 0)
                    if current <= 0:
                        continue
                    side = "yes" if pos_fp > 0 else "no"
                    entry = float(mp.get("avg_cost") or 0) * 100
                    if entry <= 0:
                        local_side, local_entry = get_local_entry(ticker)
                        if local_side and local_entry > 0:
                            side = local_side
                            entry = local_entry
                            log(f"using local entry for {ticker}: {side} @ {entry:.0f}c")
                        else:
                            log(f"EXIT SKIP {ticker}: no entry (avg_cost=0, no local)")
                            continue
                    qty = int(abs(pos_fp))

                    held_seconds = time.time() - float(mp.get("created_time") or time.time())
                    if held_seconds > 900:
                        log(f"EXIT TIMEOUT {ticker} {side} after {held_seconds:.0f}s")
                        if side == "yes":
                            result = place_order(ticker, "no", qty, int(current))
                        else:
                            result = place_order(ticker, "yes", qty, int(current))
                        log(f"EXIT ORDER {result['status']} {result['resp']}")
                        continue

                    # YES long: sell at bid if >= entry + SCALP_C
                    if side == "yes" and current >= entry + SCALP_C:
                        sell_px = int(current)
                        log(f"EXIT YES {ticker} @ {sell_px}c (entry {entry:.0f}c +{current-entry:.0f}c)")
                        result = place_order(ticker, "no", qty, sell_px, tif="immediate_or_cancel")
                        log(f"EXIT ORDER {result['status']} {result['resp']}")
                    # NO short: cover when YES drops enough that NO = entry - SCALP_C
                    elif side == "no" and current <= 100 - entry - SCALP_C:
                        cover_px = int(current)
                        log(f"EXIT NO {ticker} buy YES @ {cover_px}c (NO entry {entry:.0f}c, target NO {entry-SCALP_C:.0f}c)")
                        result = place_order(ticker, "yes", qty, cover_px, tif="immediate_or_cancel")
                        log(f"EXIT ORDER {result['status']} {result['resp']}")
            except Exception as e:
                log(f"exit ERR: {e}")

            # ---- ENTRIES: SHORT ON NEGATIVE DRIFT ----
            scores = []
            with httpx.Client(headers={"Accept-Encoding": "identity"}) as cx:
                for ticker, m in markets.items():
                    try:
                        d = drift(cx, m["pair"])
                        # For shorts: negative drift = YES falling = NO rising
                        if d <= MIN_DRIFT_PCT:
                            scores.append((d, ticker, m))
                    except Exception as e:
                        log(f"drift ERR {m['pair']}: {e}")

            if not scores:
                log("no markets pass short drift filter, sleeping 60s")
                time.sleep(60)
                continue

            scores.sort(key=lambda x: abs(x[0]), reverse=True)
            best_drift, best_ticker, best_m = scores[0]
            log(f"best short drift: {best_ticker} {best_m['pair']} {best_drift:+.2f}%")

            # Position cap
            open_count = get_open_positions_count()
            if open_count >= MAX_OPEN_POSITIONS:
                log(f"OPEN POSITION CAP: {open_count}/{MAX_OPEN_POSITIONS} — sleeping 60s")
                time.sleep(60)
                continue

            # Enter NO at the bid
            side = "no"
            price = int(best_m["no_bid"])
            count = size_position(abs(best_drift), cash)
            if count == 0:
                log("sized 0 contracts, sleeping 60s")
                time.sleep(60)
                continue

            log(f"SHORT NO {price}c x{count} {best_ticker}")
            result = place_order(best_ticker, side, count, price)
            log(f"ORDER {result['status']} {result['resp']}")
            if result["status"] == 201 and float(result["resp"].get("fill_count", 0)) > 0:
                actual_price_cents = float(result["resp"].get("average_fill_price", price)) * 100
                record_entry(best_ticker, side, actual_price_cents)

        except Exception as e:
            log(f"ERR {repr(e)[:200]}")
        time.sleep(POLL)


if __name__ == "__main__":
    main()
