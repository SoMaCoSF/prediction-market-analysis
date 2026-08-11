#!/usr/bin/env python3
"""
Order router — handles order placement, cancellation, and routing.
"""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from mission_control import KALSHI_HOST, kalshi_keys, kalshi_sign  # noqa: E402

LOG = ROOT / "logs" / "order_router.log"

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

def kalshi_post(path: str, body: dict) -> tuple[int, dict]:
    """Signed POST to Kalshi API."""
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("POST", path, ts, kpath)
    headers = {
        "KALSHI-ACCESS-KEY": kid,
        "KALSHI-ACCESS-SIGNATURE": sig,
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "Content-Type": "application/json",
    }
    r = httpx.post(f"{KALSHI_HOST}{path}", json=body, headers=headers, timeout=20)
    return r.status_code, r.json()

def place_order(ticker: str, side: str, price_cents: int, count: int,
                time_in_force: str = "good_till_canceled",
                reduce_only: bool = False) -> tuple[int, dict]:
    """Place a limit order on Kalshi."""
    price_dollars = price_cents / 100.0
    body = {
        "ticker": ticker,
        "client_order_id": f"engine-{int(time.time()*1000)}",
        "side": side,
        "count": f"{count:.2f}",
        "price": f"{price_dollars:.4f}",
        "time_in_force": time_in_force,
        "self_trade_prevention_type": "taker_at_cross",
        "post_only": False,
        "reduce_only": reduce_only,
        "subaccount": 0,
        "exchange_index": -1,
    }
    code, resp = kalshi_post("/portfolio/events/orders", body)
    log(f"ORDER {side.upper()} {ticker} {price_cents}¢ x{count} => {code}")
    return code, resp

def cancel_order(order_id: str) -> bool:
    """Cancel an order."""
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    path = f"/portfolio/orders/{order_id}"
    sig = kalshi_sign("DELETE", path, ts, kpath)
    headers = {
        "KALSHI-ACCESS-KEY": kid,
        "KALSHI-ACCESS-SIGNATURE": sig,
        "KALSHI-ACCESS-TIMESTAMP": ts,
    }
    try:
        r = httpx.delete(f"{KALSHI_HOST}{path}", headers=headers, timeout=20)
        if r.status_code == 200:
            log(f"CANCEL {order_id} => OK")
            return True
        else:
            log(f"CANCEL {order_id} => {r.status_code} {r.text[:100]}")
            return False
    except Exception as e:
        log(f"CANCEL ERROR: {e}")
        return False
