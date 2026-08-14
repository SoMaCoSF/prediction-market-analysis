#!/usr/bin/env python3
"""Depth scanner: scan all open Kalshi markets for real orderbook depth."""
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


def sign_request(private_key, method: str, path: str):
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


def depth_for_book(book: list[list[Any]]) -> float:
    if not book:
        return 0.0
    return sum(float(qty) for price, qty in book if qty is not None)


def scan_markets(private_key, limit: int = 200, offset: int = 0) -> list[dict]:
    raw = signed_get(private_key, "/markets", {"limit": str(limit), "status": "open", "offset": str(offset)})
    markets = raw.get("markets", []) if isinstance(raw, dict) else raw
    results = []
    for m in markets:
        ob = m.get("orderbook") or {}
        yes = ob.get("yes_dollars") or []
        no = ob.get("no_dollars") or []
        yes_depth = depth_for_book(yes)
        no_depth = depth_for_book(no)
        best_yes = next((float(p) for p, _ in yes if p is not None), None)
        best_no = next((float(p) for p, _ in no if p is not None), None)
        results.append({
            "ticker": m.get("ticker"),
            "title": m.get("title"),
            "volume_24h": m.get("volume_24h"),
            "yes_depth": yes_depth,
            "no_depth": no_depth,
            "best_yes": best_yes,
            "best_no": best_no,
            "liquid": yes_depth > 0 and no_depth > 0,
        })
    return results


def main():
    pk = load_key()
    print("[depth_scanner] scanning open markets for executable depth...")
    hits = []
    for offset in [0, 200, 400, 600]:
        try:
            batch = scan_markets(pk, limit=200, offset=offset)
            hits.extend(batch)
            if not batch:
                break
        except Exception as e:
            print(f"[depth_scanner] error at offset {offset}: {e}")
            break

    liquid = [h for h in hits if h["liquid"]]
    print(f"[depth_scanner] scanned={len(hits)} liquid={len(liquid)}")
    for h in liquid[:20]:
        print(
            f"[depth_scanner] {h['ticker']} | yes={h['best_yes']} no={h['best_no']} "
            f"| yes_depth={h['yes_depth']} no_depth={h['no_depth']} | vol={h['volume_24h']} | {h['title']}"
        )
    out = ROOT / "data" / "depth_scan.json"
    out.write_text(json.dumps({"scanned_at": time.time(), "liquid": liquid}, indent=2))
    print(f"[depth_scanner] wrote {out}")


if __name__ == "__main__":
    main()
