#!/usr/bin/env python3
"""Unified Kalshi execution path with real depth validation."""
import json
import os
import time
import uuid
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

ROOT = Path(__file__).resolve().parent.parent
KEY_PATH = ROOT / ".kalshi_key.pem"
BASE = "https://external-api.kalshi.com/trade-api/v2"


def signed_request(method: str, path: str, body: dict | None = None, params: dict | None = None):
    key_pem = KEY_PATH.read_text()
    private_key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    ts = str(int(time.time() * 1000))
    msg = f"{ts}{method.upper()}/trade-api/v2{path}".encode()
    sig = private_key.sign(
        msg,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    headers = {
        "KALSHI-ACCESS-KEY": os.environ["KALSHI_KEY_ID"],
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": __import__("base64").b64encode(sig).decode(),
        "Content-Type": "application/json",
    }
    url = f"{BASE}{path}"
    if method.upper() == "POST":
        return httpx.post(url, headers=headers, json=body, timeout=20)
    return httpx.get(url, headers=headers, params=params, timeout=20)


def get_orderbook(ticker: str) -> dict:
    r = signed_request("GET", f"/markets/{ticker}/orderbook")
    if r.status_code != 200:
        return {}
    return r.json().get("orderbook_fp", {})


def get_market(ticker: str) -> dict:
    r = signed_request("GET", f"/markets/{ticker}")
    if r.status_code != 200:
        return {}
    return r.json().get("market", r.json())


def validate_depth(ob: dict, side: str, price: str, count: str) -> bool:
    """Check if orderbook has enough depth for this order."""
    if side == "bid":
        levels = ob.get("yes_dollars", [])
    else:
        levels = ob.get("no_dollars", [])

    for level_price, level_count in levels:
        if level_price == price and float(level_count) >= float(count):
            return True
    return False


def place_order(ticker: str, side: str, count: float, price: float, reduce_only: bool = False) -> dict:
    """Place a Kalshi V2 order with exact schema."""
    body = {
        "ticker": ticker,
        "client_order_id": f"exec-{uuid.uuid4().hex[:8]}",
        "side": side,
        "count": f"{count:.2f}",
        "price": f"{price:.4f}",
        "time_in_force": "immediate_or_cancel" if reduce_only else "good_till_canceled",
        "self_trade_prevention_type": "taker_at_cross",
        "post_only": False,
        "cancel_order_on_pause": False,
        "reduce_only": reduce_only,
        "subaccount": 0,
        "exchange_index": 0,
    }

    r = signed_request("POST", "/portfolio/events/orders", body)
    result = {
        "ticker": ticker,
        "side": side,
        "count": count,
        "price": price,
        "reduce_only": reduce_only,
        "status_code": r.status_code,
        "response": r.text[:500],
    }

    if r.status_code == 201:
        data = r.json()
        result["order_id"] = data.get("order_id")
        result["fill_count"] = data.get("fill_count")
        result["remaining_count"] = data.get("remaining_count")
        result["avg_fill_price"] = data.get("average_fill_price")
        result["success"] = True
    else:
        result["success"] = False

    return result


def main():
    # Example: buy 1 KXELONMARS-99 YES @ 0.11 with depth check
    ticker = "KXELONMARS-99"
    side = "bid"
    count = 1.0
    price = 0.11
    reduce_only = False

    print(f"=== DEPTH CHECK {ticker} ===")
    ob = get_orderbook(ticker)
    market = get_market(ticker)

    if not ob or not market:
        print("FAIL: cannot fetch market/orderbook")
        return

    price_str = f"{price:.4f}"
    depth_ok = validate_depth(ob, side, price_str, f"{count:.2f}")

    print(f"Market: {market.get('title', ticker)}")
    print(f"Last price: {market.get('last_price_dollars')}")
    print(f"YES ask: {market.get('yes_ask_dollars')}")
    print(f"NO bid: {market.get('no_bid_dollars')}")
    print(f"Depth valid: {depth_ok}")

    if not depth_ok:
        print("SKIP: insufficient depth")
        return

    print("=== PLACING ORDER ===")
    result = place_order(ticker, side, count, price, reduce_only)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
