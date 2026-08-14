#!/usr/bin/env python3
"""Micro executor: execute cheap YES buys when depth is available."""
import json
import os
import time
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
KEY_PATH = ROOT / ".kalshi_key.pem"
BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
MAX_YES_PRICE = 0.15
SIZE = 1


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
        print(f"[micro_executor] order failed {resp.status_code}: {data}")
        return {"ok": False, "status": resp.status_code, "error": data}
    return {"ok": True, "status": resp.status_code, "data": data}


def signed_get(private_key, path: str, params: dict | None = None) -> dict:
    headers = sign_request(private_key, "GET", path)
    resp = httpx.get(BASE_URL + path, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def main():
    pk = load_key()
    depth_path = ROOT / "data" / "depth_scan.json"
    if not depth_path.exists():
        print("[micro_executor] missing depth_scan.json; run depth_scanner first")
        return

    scan = json.loads(depth_path.read_text())
    liquid = scan.get("liquid", [])
    if not liquid:
        print("[micro_executor] no liquid markets in depth_scan.json")
        return

    candidates = [m for m in liquid if m.get("best_yes") is not None and float(m["best_yes"]) <= MAX_YES_PRICE]
    if not candidates:
        print(f"[micro_executor] no cheap YES candidates <= ${MAX_YES_PRICE}")
        return

    target = sorted(candidates, key=lambda m: m.get("best_yes") or 999)[0]
    ticker = target["ticker"]
    price = float(target["best_yes"])
    print(f"[micro_executor] candidate {ticker} yes_ask={price}")

    body = {
        "ticker": ticker,
        "side": "yes",
        "action": "buy",
        "count": str(SIZE),
        "price": f"{price:.4f}",
        "client_order_id": f"micro-{int(time.time())}",
        "time_in_force": "immediate_or_cancel",
        "self_trade_prevention_type": "taker_at_cross",
    }
    result = signed_post(pk, "/portfolio/events/orders", body)
    print("[micro_executor] order result:", json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
