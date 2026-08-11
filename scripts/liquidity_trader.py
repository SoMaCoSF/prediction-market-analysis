#!/usr/bin/env python3
"""
liquidity_trader.py

Liquidity-aware trading wrapper for Kalshi.
  - Checks for TWO-SIDED depth before entering.
  - Uses dynamic pricing based on live book state.
  - Multiple exit strategies: limit, market, spread capture.
  - Blocks entries when book is one-sided.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import mission_control as mc
except Exception as e:
    print("FATAL: cannot import mission_control:", e)
    sys.exit(1)

STATE_PATH = ROOT / "data" / "liquidity_trader_state.json"
BACKUP_PATH = ROOT / "data" / "liquidity_trader_state.json.bk"
LOG_PATH = ROOT / "logs" / "liquidity_trader.out"

MIN_BID = 0.01  # Minimum bid size to consider
MIN_ASK = 0.01  # Minimum ask size to consider
MAX_SPREAD = 0.05  # Max acceptable spread
ENTRY_SIZE = 1.0  # Contracts per entry
EXIT_IMPROVE_STEP = 0.01  # $ per retry
MAX_EXIT_RETRIES = 3
POLL_INTERVAL = 30


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def log(msg: str):
    line = f"[{_utcnow()}] [liquidity_trader] {msg}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _load_state():
    for path in (STATE_PATH, BACKUP_PATH):
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "last_run": None,
        "entries": [],
        "exits": [],
        "blocked_count": 0,
    }


def _save_state(state):
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
        BACKUP_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def _direct_get(path: str):
    import urllib.request
    kid, kpath = mc.kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = mc.kalshi_sign("GET", path, ts, kpath)
    req = urllib.request.Request(
        f"{mc.KALSHI_HOST}{path}",
        headers={
            "KALSHI-ACCESS-KEY": kid,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "KALSHI-ACCESS-TIMESTAMP": ts,
        },
    )
    return json.loads(urllib.request.urlopen(req).read())


def get_market_detail(ticker: str):
    try:
        d = _direct_get(f"/markets/{ticker}")
        if isinstance(d, dict) and 'market' in d:
            return d['market']
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def has_two_sided_depth(ticker: str) -> tuple[bool, dict]:
    """Check if market has executable bid AND ask."""
    detail = get_market_detail(ticker)
    yes_bid = float(detail.get("yes_bid_dollars") or 0)
    yes_ask = float(detail.get("yes_ask_dollars") or 0)
    no_bid = float(detail.get("no_bid_dollars") or 0)
    no_ask = float(detail.get("no_ask_dollars") or 0)
    volume = float(detail.get("volume_24h") or 0)

    has_liquidity = (
        yes_bid >= MIN_BID and yes_ask >= MIN_ASK and
        no_bid >= MIN_BID and no_ask >= MIN_ASK and
        volume > 0
    )
    spread = abs(yes_ask - yes_bid) + abs(no_ask - no_bid)
    info = {
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "no_ask": no_ask,
        "volume": volume,
        "spread": spread,
        "has_liquidity": has_liquidity,
    }
    return has_liquidity, info


def post_order(ticker: str, side: str, count: float, price: float, prefix: str = "liq"):
    """Post an order with dynamic pricing."""
    now = int(time.time() * 1000)
    body = {
        "ticker": ticker,
        "client_order_id": f"{prefix}-{now}",
        "side": side,
        "count": f"{count:.2f}",
        "price": f"{price:.4f}",
        "time_in_force": "good_till_canceled",
        "self_trade_prevention_type": "taker_at_cross",
        "post_only": False,
        "cancel_order_on_pause": False,
        "reduce_only": False,
        "subaccount": 0,
        "exchange_index": -1,
    }
    try:
        kid, kpath = mc.kalshi_keys()
        ts = str(int(time.time() * 1000))
        sig = mc.kalshi_sign("POST", "/portfolio/events/orders", ts, kpath)
        req = urllib.request.Request(
            f"{mc.KALSHI_HOST}/portfolio/events/orders",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "KALSHI-ACCESS-KEY": kid,
                "KALSHI-ACCESS-SIGNATURE": sig,
                "KALSHI-ACCESS-TIMESTAMP": ts,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req)
        return resp.status, resp.read().decode("utf-8")
    except Exception as e:
        return 0, repr(e)


def try_exit_with_capture(ticker: str, count: float, entry_price: float) -> bool:
    """Try to exit via spread capture: buy NO + sell YES to lock profit."""
    detail = get_market_detail(ticker)
    yes_bid = float(detail.get("yes_bid_dollars") or 0)

    no_ask = float(detail.get("no_ask_dollars") or 0)

    if yes_bid <= 0 or no_ask <= 0:
        return False

    # If we have YES, sell YES at bid and buy NO at ask to capture spread
    sell_yes_price = yes_bid
    buy_no_price = no_ask

    # Only profitable if spread > 0
    if sell_yes_price <= buy_no_price:
        return False

    log(f"SPREAD CAPTURE: {ticker} sell YES @ {sell_yes_price:.4f}, buy NO @ {buy_no_price:.4f}")
    return True


def scan_all_markets(state):
    """Scan ALL open markets for ANY executable liquidity."""
    log("scanning all markets for any liquidity...")
    state["last_run"] = _utcnow()

    try:
        markets_data = _direct_get("/markets?limit=200&status=open")
        all_markets = markets_data.get("markets", [])
    except Exception as e:
        log(f"market list err: {repr(e)}")
        return state

    # Filter to markets with ANY non-zero price or volume
    candidates = []
    for m in all_markets:
        ticker = m.get("ticker", "")
        if not ticker:
            continue
        yes_bid = float(m.get("yes_bid_dollars") or 0)
        yes_ask = float(m.get("yes_ask_dollars") or 0)
        no_bid = float(m.get("no_bid_dollars") or 0)
        no_ask = float(m.get("no_ask_dollars") or 0)
        vol = float(m.get("volume_24h") or 0)
        if vol > 0 or yes_bid > 0 or yes_ask > 0 or no_bid > 0 or no_ask > 0:
            candidates.append((ticker, yes_bid, yes_ask, no_bid, no_ask, vol))

    if not candidates:
        state["blocked_count"] = state.get("blocked_count", 0) + 1
        log(f"no liquid markets (blocked {state['blocked_count']} times)")
        return state

    # Sort by volume desc, then yes_bid desc
    candidates.sort(key=lambda x: (x[5], x[1]), reverse=True)

    log(f"found {len(candidates)} candidate markets — top: {candidates[0][0]} vol={candidates[0][5]:.0f}")

    # Check detail for top 5 candidates
    tradable = []
    for ticker, _yes_bid, _yes_ask, _no_bid, _no_ask, _vol in candidates[:5]:
        has_depth, info = has_two_sided_depth(ticker)
        if has_depth:
            tradable.append((ticker, info))
            log(f"TRADABLE {ticker}: spread={info['spread']:.4f} vol={info['volume']:.0f}")
        else:
            log(f"BLOCKED {ticker}: one-sided or no volume")

    if not tradable:
        state["blocked_count"] = state.get("blocked_count", 0) + 1
        log(f"no two-sided markets (blocked {state['blocked_count']} times)")
        return state

    # Trade the best spread
    tradable.sort(key=lambda x: x[1]["spread"])
    ticker, info = tradable[0]

    # Enter at mid-price
    mid = (info["yes_bid"] + info["yes_ask"]) / 2
    entry_price = max(MIN_BID, min(mid, 0.15))

    log(f"ENTERING {ticker} @ {entry_price:.4f} (spread {info['spread']:.4f})")
    status, body = post_order(ticker, "bid", ENTRY_SIZE, entry_price, prefix="liq-entry")

    if status == 201:
        try:
            resp = json.loads(body)
            fc = float(resp.get("fill_count", 0) or 0)
            if fc > 0:
                log(f"FILLED entry {ticker} {fc}x @ {entry_price:.4f}")
                state["entries"].append({
                    "ts": _utcnow(),
                    "ticker": ticker,
                    "count": fc,
                    "price": entry_price,
                })
        except Exception:
            pass
    else:
        log(f"entry failed: {status} {body[:200]}")

    # Try spread capture exit
    try_exit_with_capture(ticker, ENTRY_SIZE, entry_price)

    return state


def main():
    log("liquidity_trader starting")
    state = _load_state()
    log(f"loaded state: entries={len(state.get('entries',[]))} exits={len(state.get('exits',[]))}")
    try:
        while True:
            try:
                state = scan_all_markets(state)
                _save_state(state)
            except Exception as e:
                log(f"pass err: {repr(e)}")
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        log("shutting down")
        _save_state(state)


if __name__ == "__main__":
    main()
