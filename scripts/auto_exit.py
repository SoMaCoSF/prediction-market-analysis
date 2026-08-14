#!/usr/bin/env python3
"""Auto exit: scan positions, find any executable depth, close immediately."""
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
KEY_PATH = ROOT / ".kalshi_key.pem"
BASE_URL = "https://external-api.kalshi.com/trade-api/v2"


def load_key():
    pem = KEY_PATH.read_text()
    return serialization.load_pem_private_key(pem.encode(), password=None)


def sign_request(private_key, method: str, path: str, body: bytes = b""):
    ts = str(int(time.time() * 1000))
    msg = f"{ts}{method}/trade-api/v2{path}".encode()
    sig = private_key.sign(
        msg,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": os.environ["KALSHI_KEY_ID"],
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": __import__("base64").b64encode(sig).decode(),
    }


def signed_get(private_key, path: str, params: dict | None = None) -> dict:
    headers = sign_request(private_key, "GET", path)
    resp = httpx.get(BASE_URL + path, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def signed_post(private_key, path: str, body: dict) -> dict:
    headers = sign_request(private_key, "POST", path, json.dumps(body).encode())
    headers["Content-Type"] = "application/json"
    resp = httpx.post(BASE_URL + path, headers=headers, json=body, timeout=20)
    text = resp.text
    try:
        data = resp.json()
    except Exception:
        data = {"raw": text}
    if resp.status_code >= 400:
        print(f"[auto_exit] exit failed {resp.status_code}: {data}")
        return {"ok": False, "status": resp.status_code, "error": data}
    return {"ok": True, "status": resp.status_code, "data": data}


def depth_for_book(book: list[list[Any]]) -> float:
    if not book:
        return 0.0
    return sum(float(qty) for _, qty in book if qty is not None)


def main():
    pk = load_key()
    positions = signed_get(pk, "/portfolio/positions", {"limit": "200"})
    event_positions = positions.get("event_positions", []) if isinstance(positions, dict) else []
    if not event_positions:
        print("[auto_exit] no positions found")
        return

    # Build ticker map
    pos_map = {}
    for p in event_positions:
        ticker = p.get("event_ticker") or p.get("ticker")
        if not ticker:
            continue
        pos_map.setdefault(ticker, []).append(p)

    print(f"[auto_exit] scanning {len(pos_map)} tickers for exit depth...")

    for ticker in list(pos_map.keys()):
        try:
            m = signed_get(pk, f"/markets/{ticker}").get("market", {})
        except Exception as e:
            print(f"[auto_exit] market fetch failed {ticker}: {e}")
            continue

        ob = m.get("orderbook") or {}
        yes = ob.get("yes_dollars") or []
        no = ob.get("no_dollars") or []
        yes_depth = depth_for_book(yes)
        no_depth = depth_for_book(no)
        best_bid = next((float(p) for p, _ in no if p is not None), None)
        print(f"[auto_exit] {ticker} yes_depth={yes_depth} no_depth={no_depth} best_bid={best_bid}")

        if yes_depth > 0 and no_depth > 0 and best_bid is not None:
            size = sum(float(p.get("total_cost_shares_fp") or p.get("count") or 0) for p in pos_map[ticker])
            if size <= 0:
                continue
            body = {
                "ticker": ticker,
                "side": "yes",
                "action": "sell",
                "count": str(size),
                "price": f"{best_bid:.4f}",
                "client_order_id": f"exit-{int(time.time())}",
                "time_in_force": "immediate_or_cancel",
                "self_trade_prevention_type": "taker_at_cross",
            }
            result = signed_post(pk, "/portfolio/events/orders", body)
            print(f"[auto_exit] exit order for {ticker}:", json.dumps(result, indent=2))
        else:
            print(f"[auto_exit] {ticker} no executable depth, skip")


if __name__ == "__main__":
    main()
