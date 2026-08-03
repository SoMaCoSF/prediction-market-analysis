# file_id: SOM-PY-0957-v1.0.0 name: maker_engine.py description: Maker engine — zero-fee resting bids below mid on KXBTC15M in calm tape, GTD self-expiring quotes, inventory cap, sells into strength; structural spread capture; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [maker, liquidity, spread, zero-fee, btc] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""maker_engine.py — the structural loop: be the house, small.

Calm tape only (|24h drift| < CALM_DRIFT): post a resting BID at bid-1c
(maker = zero fee on Kalshi), 1 contract, GTD 90s (self-expiring, no cancel
endpoint needed). When holding inventory and the book rallies, offer it back
at ask (taker exit, capped). Hard caps: MAX_INV contracts, cash floor, kill.
Edge: repeatedly buying 1-2c under mid in a mean-reverting 15M book.
"""
from __future__ import annotations

import base64
import hashlib
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import httpx  # noqa: E402
import runlog  # noqa: E402
import sb  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
MC = os.getenv("MC_URL", "http://127.0.0.1:8420")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
PK = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()

CALM_DRIFT = 0.15       # only quote when |24h drift| below this %
QUOTE_S = 45            # re-quote cadence
GTD_S = 90              # quote self-expiry
MAX_INV = 3             # max contracts held
FLOOR = 5.00
EDGE_C = 1              # bid 1c below current best bid

inv = 0
session_pnl = 0.0


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)
    runlog.log_event("maker", m)


def _sign(method, path, ts):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key((ROOT / ".kalshi_key.pem").read_bytes(), password=None)
    sig = key.sign(f"{ts}{method}{path}".encode(),
                   padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                   hashes.SHA256())
    return base64.b64encode(sig).decode()


def kget(path):
    try:
        ts = str(int(time.time() * 1000))
        full = "/trade-api/v2" + path.split("?")[0]
        h = {"KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"),
             "KALSHI-ACCESS-SIGNATURE": _sign("GET", full, ts),
             "KALSHI-ACCESS-TIMESTAMP": ts}
        r = httpx.get(KALSHI + path, headers=h, timeout=15)
        return r.json() if "json" in r.headers.get("content-type", "") else {}
    except Exception:
        return {}


def cash():
    return float(kget("/portfolio/balance").get("balance_dollars") or 0)


def fire(ticker, side, price, exp_ts=None):
    body = {"ticker": ticker, "side": side, "price": price, "count": 1,
            "mode": "live", "passkey": PK, "confirm": "FIRE"}
    if exp_ts:
        body["expiration_ts"] = exp_ts
    try:
        r = httpx.post(f"{MC}/api/order", json=body, timeout=30)
        d = r.json()
        return {"ok": bool(d.get("ok")), "filled": float((d.get("ack") or {}).get("fill_count") or 0)}
    except Exception as e:
        return {"ok": False, "filled": 0.0, "err": repr(e)[:60]}


def btc_drift(cx):
    d = cx.get("https://api.kraken.com/0/public/Ticker?pair=XBTUSD", timeout=10).json()["result"]
    k = next(iter(d))
    return (float(d[k]["c"][0]) - float(d[k]["o"])) / float(d[k]["o"]) * 100


def window_book(cx):
    r = cx.get(f"{KALSHI}/markets", params={"limit": 3, "status": "open", "series_ticker": "KXBTC15M"}, timeout=15)
    for m in r.json().get("markets", []):
        ya = float(m.get("yes_ask_dollars") or 0)
        if not (0 < ya < 1):
            continue
        close = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
        if close - time.time() < 180:
            continue
        return {"ticker": m["ticker"], "ya": round(ya * 100), "yb": round(float(m.get("yes_bid_dollars") or 0) * 100)}
    return None


def main():
    global inv, session_pnl
    fleetlib.acquire_lock("maker")
    log(f"maker start | calm<{CALM_DRIFT}% edge -{EDGE_C}c GTD {GTD_S}s inv<={MAX_INV} floor=${FLOOR}")
    with httpx.Client(headers={"Accept-Encoding": "identity"}) as cx:
        while True:
            fleetlib.checkin("maker")
            try:
                if cash() < FLOOR:
                    time.sleep(QUOTE_S * 2)
                    continue
                d = btc_drift(cx)
                b = window_book(cx)
                if not b or abs(d) >= CALM_DRIFT:
                    time.sleep(QUOTE_S)
                    continue
                if inv < MAX_INV:
                    bid_px = b["yb"] - EDGE_C
                    if 3 <= bid_px <= 97:
                        r = fire(b["ticker"], "yes", bid_px, exp_ts=int(time.time()) + GTD_S)
                        if r["ok"] and r["filled"] > 0:
                            inv += 1
                            log(f"MAKER-FILL bid {bid_px}c (book {b['yb']}/{b['ya']}) inv={inv}")
                elif inv > 0 and b["ya"] >= 90:
                    r = fire(b["ticker"], "no", 100 - b["ya"])
                    if r["ok"] and r["filled"] > 0:
                        inv -= 1
                        log(f"MAKER-OUT ask {b['ya']}c inv={inv}")
            except Exception as e:
                log(f"cycle warn {repr(e)[:60]}")
            time.sleep(QUOTE_S)


if __name__ == "__main__":
    sys.exit(main())
