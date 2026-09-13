#!/usr/bin/env python3
"""kalshi_executor.py — GO-gated execution path for the /loop uptick monitor.

Design:
  - NEVER trades unless BOTH conditions hold:
      1. Venue has real liquidity (vol24h>0 AND two-sided spread) — set by caller
      2. A GO file exists at prediction-market-analysis/GO_TRADE (explicit user authorization)
  - DRY_RUN=True by default: builds exact V2 request, validates depth, but does
    NOT POST. Set DRY_RUN=False only via the GO path.
  - Hard rails: CASH_FLOOR=10.00, MAX_OPEN_POSITIONS=3, MAX_CONTRACTS_PER_ORDER=2,
    MIN_VOLUME=50, mean-reversion entry only (YES<15c or YES>85c).
  - Trusts fills, not quotes: a 201 is NOT a fill — checks fill_count>0.

Reuses mission_control.kalshi_keys / kalshi_sign so auth stays in one place.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

import httpx  # noqa: E402
from mission_control import KALSHI_HOST, kalshi_keys, kalshi_sign  # noqa: E402

GO_FILE = ROOT / "GO_TRADE"
LOG_FILE = ROOT / "data" / "executor.log"
LOG_FILE.parent.mkdir(exist_ok=True)

# ---- risk rails (non-negotiable) ----
CASH_FLOOR = 10.00
MAX_OPEN_POSITIONS = 3
MAX_CONTRACTS_PER_ORDER = 2
MIN_VOLUME = 50          # min real volume (volume_fp) to consider a market
MIN_TTL = 120            # 15M books: reject only markets closing within 2 min
SCALP_C = 5              # exit when +5c
STOP_C = 3
REVERSION_THRESHOLD = 15 # YES<15c buy YES; YES>85c buy NO
MAX_ENTRY_PRICE = 100 - SCALP_C - 2

# Series that reliably carry live two-sided books. The default /markets
# pagination never reaches them (first pages are KXMVE shard listings), and
# their volume only appears in `volume_fp` (volume/volume_24h read null on
# this endpoint for every crypto/sports market).
HOT_SERIES = ["KXBTC15M", "KXETH15M", "KXSOL15M", "KXXRP15M", "KXDOGE15M", "KXNFLGAME"]


def real_vol(m: dict) -> float:
    """Return real traded volume: volume_fp is the populated field on /markets."""
    for k in ("volume_fp", "volume_24h_fp", "volume_24h", "volume"):
        v = m.get(k)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return 0.0


def log(msg: str, kind: str = "info") -> None:
    line = f"[{datetime.now(timezone.utc).isoformat()[:19]}Z][{kind}] {msg}"
    print(line, flush=True)
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")


def go_active() -> bool:
    """Explicit user authorization to trade live. File must exist."""
    return GO_FILE.exists()


def dry_run() -> bool:
    """Default safe mode. Only live when GO present AND caller forces live."""
    return not go_active()


def get_cash() -> float:
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("GET", "/portfolio/balance", ts, kpath)
    h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}
    r = httpx.get(f"{KALSHI_HOST}/portfolio/balance", headers=h, timeout=15)
    r.raise_for_status()
    return float(r.json().get("balance_dollars", 0) or 0)


def get_open_positions() -> list:
    """Open positions. NOTE: the response key is `market_positions` (sometimes
    `event_positions`) — there is no `positions` key (reading it shows 0)."""
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("GET", "/portfolio/positions", ts, kpath)
    h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}
    r = httpx.get(f"{KALSHI_HOST}/portfolio/positions", headers=h, timeout=20)
    r.raise_for_status()
    d = r.json()
    return d.get("market_positions") or d.get("event_positions") or d.get("positions") or []
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("GET", "/portfolio/positions", ts, kpath)
    h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}
    r = httpx.get(f"{KALSHI_HOST}/portfolio/positions?status=open&limit=200", headers=h, timeout=15)
    r.raise_for_status()
    return r.json().get("positions", [])


def get_orderbook(ticker: str) -> dict:
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("GET", f"/markets/{ticker}/orderbook", ts, kpath)
    h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}
    r = httpx.get(f"{KALSHI_HOST}/markets/{ticker}/orderbook", headers=h, timeout=15)
    if r.status_code != 200:
        return {}
    return r.json().get("orderbook_fp", {})


def scan_liquid_markets(limit: int = 200) -> dict:
    """Return {ticker: {yes_ask, yes_bid, volume, close}} for tradeable markets.

    Fetches the default open pages (capped, no infinite-loop hangs) PLUS the
    HOT_SERIES by series_ticker — the default pagination never reaches the
    live crypto/NFL books. Volume comes from real_vol() (`volume_fp`); quotes
    from *_dollars fields (the int-cent fields are absent on /markets).
    """
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("GET", "/markets", ts, kpath)
    h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}
    raw = []
    cursor = None
    batches = 0
    while len(raw) < limit and batches < 3:
        batches += 1
        params = {"limit": 100, "status": "open"}
        if cursor:
            params["cursor"] = cursor
        r = httpx.get(f"{KALSHI_HOST}/markets", params=params, headers=h, timeout=15)
        if r.status_code != 200:
            break
        j = r.json()
        raw.extend(j.get("markets", []))
        cursor = j.get("cursor")
        if not cursor:
            break
    for s in HOT_SERIES:
        try:
            r = httpx.get(
                f"{KALSHI_HOST}/markets",
                params={"limit": 10, "status": "open", "series_ticker": s},
                headers=h,
                timeout=15,
            )
            if r.status_code == 200:
                raw.extend(r.json().get("markets", []))
        except Exception:
            continue
    out = {}
    for m in raw:
        ticker = m.get("ticker") or ""
        if not ticker.startswith("KX") or ticker in out:
            continue
        ya = float(m.get("yes_ask_dollars", 0) or 0) * 100
        yb = float(m.get("yes_bid_dollars", 0) or 0) * 100
        vol = real_vol(m)
        close = m.get("close_time")
        if yb > 0 and ya > 0 and 1 <= ya <= MAX_ENTRY_PRICE and vol >= MIN_VOLUME and close:
            try:
                close_ts = datetime.fromisoformat(close.replace("Z", "+00:00")).timestamp()
                if close_ts - time.time() < MIN_TTL:
                    continue
            except Exception:
                pass
            out[ticker] = {"yes_ask": ya, "yes_bid": yb, "volume": vol, "close": close}
    return out


def mean_reversion_signal(m: dict):
    ya = m["yes_ask"]
    vol = m["volume"]
    if ya < REVERSION_THRESHOLD:
        return "yes", int(ya), min(vol / 1000.0, 1.0)
    if ya > 100 - REVERSION_THRESHOLD:
        return "no", int(100 - ya), min(vol / 1000.0, 1.0)
    return None, None, None


def validate_depth(ob: dict, side: str, price: str, count: str) -> bool:
    """Check if orderbook has enough depth for this order at the given price.

    Orderbook levels arrive as [price_float, count_float]; compare by rounded
    float (not string) to avoid '0.12' vs '0.1200' mismatches.
    """
    levels = ob.get("yes_dollars", []) if side == "bid" else ob.get("no_dollars", [])
    target = round(float(price), 4)
    for level_price, level_count in levels:
        if round(float(level_price), 4) == target and float(level_count) >= float(count):
            return True
    return False


def build_order(ticker: str, side_v1: str, count: int, price_cents: int, tif: str = "good_till_canceled", reduce_only: bool = False) -> dict:
    v2_side = "bid" if side_v1 == "yes" else "ask"
    v2_price = price_cents / 100.0 if side_v1 == "yes" else (100 - price_cents) / 100.0
    return {
        "ticker": ticker,
        "client_order_id": f"exec-{int(time.time()*1000)}",
        "side": v2_side,
        "count": f"{count:.2f}",
        "price": f"{v2_price:.4f}",
        "time_in_force": tif,
        "self_trade_prevention_type": "taker_at_cross",
        "post_only": False,
        "cancel_order_on_pause": False,
        "reduce_only": reduce_only,
        "subaccount": 0,
        "exchange_index": 0,
    }


def post_order(body: dict, live: bool) -> dict:
    """POST /portfolio/events/orders. If not live, return a dry-run record."""
    if not live:
        return {"live": False, "would_post": body, "success": None}
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("POST", "/portfolio/events/orders", ts, kpath)
    h = {
        "KALSHI-ACCESS-KEY": kid,
        "KALSHI-ACCESS-SIGNATURE": sig,
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "Content-Type": "application/json",
    }
    r = httpx.post(f"{KALSHI_HOST}/portfolio/events/orders", json=body, headers=h, timeout=20)
    res = {"live": True, "status_code": r.status_code, "response": r.text[:500]}
    if r.status_code == 201:
        d = r.json()
        res.update({
            "order_id": d.get("order_id"),
            "fill_count": d.get("fill_count"),
            "remaining_count": d.get("remaining_count"),
            "avg_fill_price": d.get("average_fill_price"),
            "success": float(d.get("fill_count", 0) or 0) > 0,
        })
    else:
        res["success"] = False
    return res


def execute_once(force_live: bool = False) -> dict:
    """One execution cycle. Returns a status dict. Respects all rails."""
    report = {"ts": datetime.now(timezone.utc).isoformat(), "action": "none", "detail": ""}
    live = force_live and go_active()
    if force_live and not go_active():
        report["action"] = "blocked"
        report["detail"] = "force_live requested but GO_TRADE absent — refusing live trade"
        log("EXECUTE blocked: GO_TRADE file absent", "warn")
        return report

    cash = get_cash()
    if cash < CASH_FLOOR:
        report["action"] = "hold"
        report["detail"] = f"cash ${cash:.2f} at/below floor ${CASH_FLOOR:.2f}"
        log(f"EXECUTE hold: cash ${cash:.2f} <= floor", "info")
        return report

    markets = scan_liquid_markets()
    if not markets:
        report["action"] = "hold"
        report["detail"] = "no liquid markets (venue dead)"
        log("EXECUTE hold: no liquid markets", "info")
        return report

    # exits first
    positions = get_open_positions()
    open_count = sum(1 for p in positions if float(p.get("position_fp", 0) or 0) != 0)
    for p in positions:
        pos_fp = float(p.get("position_fp", 0) or 0)
        if pos_fp == 0:
            continue
        ticker = p.get("ticker")
        if ticker not in markets:
            continue
        m = markets[ticker]
        current = float(m.get("yes_bid", 0) or 0)
        if current <= 0:
            continue
        side = "yes" if pos_fp > 0 else "no"
        entry = float(p.get("avg_cost", 0) or 0) * 100
        if entry <= 0:
            continue
        held = time.time() - float(p.get("created_time", time.time()))
        should_exit = held > 900 or (side == "yes" and current >= entry + SCALP_C) or (side == "no" and current <= 100 - entry - SCALP_C)
        if should_exit:
            body = build_order(ticker, "no" if side == "yes" else "yes", int(abs(pos_fp)), int(current), tif="immediate_or_cancel", reduce_only=True)
            res = post_order(body, live)
            log(f"EXIT {ticker} side={side} live={live} -> {res.get('status_code', res.get('would_post') and 'DRY')}")
            report["action"] = "exit"
            report["detail"] = f"{ticker} exit submitted (live={live})"
            return report

    if open_count >= MAX_OPEN_POSITIONS:
        report["action"] = "hold"
        report["detail"] = f"position cap {open_count}/{MAX_OPEN_POSITIONS}"
        log(f"EXECUTE hold: cap {open_count}/{MAX_OPEN_POSITIONS}", "info")
        return report

    candidates = []
    for ticker, m in markets.items():
        side, price, conf = mean_reversion_signal(m)
        if side and price and conf > 0:
            candidates.append((conf, ticker, side, price, m["volume"]))
    if not candidates:
        report["action"] = "hold"
        report["detail"] = "no mean-reversion candidates"
        log("EXECUTE hold: no MR candidates", "info")
        return report

    candidates.sort(key=lambda x: x[0], reverse=True)
    _, ticker, side, price, vol = candidates[0]
    risk = max(cash - CASH_FLOOR, 0)
    count = min(max(int(risk * 0.20 / 0.01), 1), MAX_CONTRACTS_PER_ORDER)

    # real depth validation
    ob = get_orderbook(ticker)
    price_str = f"{price:.4f}"
    if not validate_depth(ob, "bid" if side == "yes" else "ask", price_str, f"{count:.2f}"):
        report["action"] = "skip"
        report["detail"] = f"{ticker} insufficient depth at {price}c x{count}"
        log(f"EXECUTE skip: {ticker} no depth @ {price}c", "warn")
        return report

    body = build_order(ticker, side, count, price, tif="good_till_canceled")
    res = post_order(body, live)
    log(f"ENTRY {side.upper()} {ticker} @ {price}c x{count} live={live} -> {res.get('status_code', 'DRY')} fill={res.get('fill_count')}")
    report["action"] = "entry"
    report["detail"] = f"{side} {ticker} @ {price}c x{count} (live={live}) -> {res.get('status_code', 'DRY_RUN')}"
    report["result"] = res
    return report


if __name__ == "__main__":
    # Default: DRY_RUN (no GO file). Prove the path is wired without risking capital.
    out = execute_once(force_live=False)
    print(json.dumps(out, indent=2, default=str))
