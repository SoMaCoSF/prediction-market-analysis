#!/usr/bin/env python3
"""sell_wti_ladder.py — sell the dormant WTI Nov-3 ladder at live bids.

Pattern: probe-first (1 contract), then IoC sweep per leg, reduce_only.
Order body MIRRORS the working gods-eye rail (src/prediction/tradeCore.mjs
buildV2OrderBody) — crucially `exchange_index: -1` (auto-route the shard by
ticker). Forcing exchange_index 0/2 on a direct POST causes
`404 market_not_found` even though the market reads fine (learned 2026-09-13).

Usage:
  .venv311/Scripts/python scripts/sell_wti_ladder.py [--dry]
"""
import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
KID = os.getenv("KALSHI_KEY_ID")
KEY = serialization.load_pem_private_key((ROOT / ".kalshi_key.pem").read_bytes(), password=None)
BASE = "https://api.elections.kalshi.com/trade-api/v2"
DRY = "--dry" in sys.argv


def sign(method: str, path: str, ts: str) -> str:
    msg = f"{ts}{method}/trade-api/v2{path.split('?')[0]}".encode()
    return base64.b64encode(
        KEY.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
    ).decode()


def get(path: str):
    ts = str(int(time.time() * 1000))
    h = {"KALSHI-ACCESS-KEY": KID, "KALSHI-ACCESS-SIGNATURE": sign("GET", path, ts), "KALSHI-ACCESS-TIMESTAMP": ts}
    r = httpx.get(BASE + path, headers=h, timeout=20)
    return r.status_code, r.json()


def post_order(body: dict):
    if DRY:
        return 0, {"dry": body}
    ts = str(int(time.time() * 1000))
    h = {
        "KALSHI-ACCESS-KEY": KID,
        "KALSHI-ACCESS-SIGNATURE": sign("POST", "/portfolio/events/orders", ts),
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "Content-Type": "application/json",
    }
    r = httpx.post(BASE + "/portfolio/events/orders", headers=h, json=body, timeout=25)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text[:300]}
    return r.status_code, j


def best_bid(leg: str):
    _, ob = get(f"/markets/{leg}/orderbook")
    levels = sorted(((float(p), float(c)) for p, c in ob.get("orderbook_fp", {}).get("yes_dollars", [])), key=lambda x: -x[0])
    levels = [(p, c) for p, c in levels if c >= 0.5]
    return levels[0] if levels else (None, None)


def sell(leg: str, count: int, price: float, tag: str):
    body = {
        "ticker": leg,
        "client_order_id": f"wti-sweep-{tag}-{int(time.time() * 1000)}",
        "side": "ask",
        "count": f"{int(count)}.00",
        "price": f"{price:.4f}",
        "time_in_force": "immediate_or_cancel",
        "self_trade_prevention_type": "taker_at_cross",
        "post_only": False,
        "cancel_order_on_pause": False,
        "reduce_only": True,
        "subaccount": 0,
        "exchange_index": -1,  # auto-route the shard by ticker — the only value that works
    }
    st, j = post_order(body)
    return st, float(j.get("fill_count") or 0), j


def main() -> None:
    st, d = get("/portfolio/positions?limit=200")
    mp = d.get("market_positions") or d.get("event_positions") or []
    holds = {
        p["ticker"]: abs(float(p["position_fp"]))
        for p in mp
        if str(p.get("ticker", "")).startswith("KXWTI-26NOV03") and float(p.get("position_fp") or 0) != 0
    }
    print("WTI holdings:", json.dumps(holds))
    if not holds:
        print("nothing to sell")
        return

    total = 0.0
    probe_leg = max(holds, key=holds.get)
    p, _ = best_bid(probe_leg)
    print(f"PROBE: sell 1x {probe_leg} @ {p}")
    st, fc, j = sell(probe_leg, 1, p, "probe")
    print("  ->", st, "fill:", fc, str(j)[:200])
    if fc <= 0 and not DRY:
        print("probe failed — stopping before sweep (no spray)")
        return
    holds[probe_leg] -= 1
    total += fc * (p or 0)

    print("=== SWEEP ===")
    for leg, cnt in holds.items():
        cnt = int(round(cnt))
        while cnt > 0:
            p, _ = best_bid(leg)
            if p is None or p < 0.03:
                print(f"  {leg:28s} x{cnt:2d} SKIP (bid < 3c)")
                break
            st, fc, j = sell(leg, cnt, p, "sweep")
            got = int(round(fc))
            print(f"  {leg:28s} x{cnt:2d} @ {p:.2f} -> HTTP {st} filled {got}")
            if got > 0:
                total += got * p
                cnt -= got
            else:
                if st != 201:
                    print("    ", str(j)[:200])
                break

    st, bal = get("/portfolio/balance")
    print(f"\nTOTAL PROCEEDS: ${total:.2f}")
    print("NEW BALANCE:", {k: bal.get(k) for k in ("balance", "balance_dollars", "portfolio_value")})


if __name__ == "__main__":
    main()
