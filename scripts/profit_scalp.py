# file_id: SOM-PY-0937-v1.0.0 name: profit_scalp.py description: Speed-run scalp engine — early-window drift entries + reprice exits at +15c (no settlement wait), exchange-truth state, micro size, bankroll guard project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [scalp, hft, momentum, kalshi, live, speedrun] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""profit_scalp.py — the speed run.

Loop (5s cadence):
  ENTER: early 15M window (ttl>=540s), drift>=±0.20%, price<=60c, 1 contract.
  EXIT : held YES whose bid >= entry+SCALP_C -> sell at bid (taker) NOW.
         Profit is locked at reprice, not at settlement -> many cycles/hour.
  Truth: open positions read from the EXCHANGE every cycle (no local-state drift).
  Guard: cash floor $20, session stop -$3, MC kill switch honored, one position
         per series at a time.

Sell mechanics: selling YES at bid B == V2 ask @ B/100, which our MC translator
produces from side='no' price=(100-B). Minted as 0x3A5 ORDER_ASK in the ledger.
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
import httpx  # noqa: E402
import sb  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
MC = os.getenv("MC_URL", "http://127.0.0.1:8420")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
PK = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()

SERIES = [("KXBTC15M", "XBTUSD"), ("KXETH15M", "ETHUSD"), ("KXSOL15M", "SOLUSD"),
          ("KXXRP15M", "XRPUSD"), ("KXDOGE15M", "DOGEUSD")]
DRIFT_MIN, ENTRY_MAX, TTL_MIN = 0.20, 60, 540
SCALP_C = 15               # exit when bid >= entry + this many cents
CASH_FLOOR = 20.00
SESSION_STOP = -300
POLL = 5
MAX_OPEN = 5

session_pnl = 0.0


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def _sign(method, path, ts):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key((ROOT / ".kalshi_key.pem").read_bytes(), password=None)
    sig = key.sign(f"{ts}{method}{path}".encode(),
                   padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                   hashes.SHA256())
    return base64.b64encode(sig).decode()


def kget(path):
    ts = str(int(time.time() * 1000))
    full = "/trade-api/v2" + path.split("?")[0]
    h = {"KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"),
         "KALSHI-ACCESS-SIGNATURE": _sign("GET", full, ts),
         "KALSHI-ACCESS-TIMESTAMP": ts}
    r = httpx.get(KALSHI + path, headers=h, timeout=15)
    return r.json() if "json" in r.headers.get("content-type", "") else {}


def cash() -> float:
    return float(kget("/portfolio/balance").get("balance_dollars") or 0)


def positions() -> dict:
    """truth: ticker -> {fp, cost_per_ct, side} for 15M markets."""
    out = {}
    d = kget("/portfolio/positions?limit=100")
    for mp in d.get("market_positions", []):
        t = mp.get("ticker", "")
        fp = float(mp.get("position_fp") or 0)
        if fp <= 0 or "15M" not in t:
            continue
        cost = float(mp.get("total_traded_dollars") or 0)
        out[t] = {"fp": fp, "entry_c": round(cost / fp * 100, 1) if fp else 0, "side": "yes"}
    return out


def drift(cx, pair):
    d = cx.get(f"https://api.kraken.com/0/public/Ticker?pair={pair}", timeout=10).json()["result"]
    k = next(iter(d))
    return (float(d[k]["c"][0]) - float(d[k]["o"])) / float(d[k]["o"]) * 100


def book(cx, ticker):
    r = cx.get(f"{KALSHI}/markets/{ticker}", timeout=15)
    m = r.json().get("market") or {}
    return {"ya": float(m.get("yes_ask_dollars") or 0) * 100,
            "yb": float(m.get("yes_bid_dollars") or 0) * 100,
            "status": m.get("status")}


def window_market(cx, series):
    r = cx.get(f"{KALSHI}/markets", params={"limit": 5, "status": "open", "series_ticker": series}, timeout=15)
    for m in r.json().get("markets", []):
        ya = float(m.get("yes_ask_dollars") or 0)
        if not (0 < ya < 1):
            continue
        ttl = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).astimezone(timezone.utc).timestamp() - time.time()
        if ttl >= TTL_MIN:
            return {"ticker": m["ticker"], "ya": round(ya * 100), "yb": round(float(m.get("yes_bid_dollars") or 0) * 100), "ttl": ttl}
    return None


def fire(ticker, side, price, count=1):
    r = httpx.post(f"{MC}/api/order", json={"ticker": ticker, "side": side, "price": price,
                   "count": count, "mode": "live", "passkey": PK, "confirm": "FIRE"}, timeout=30)
    d = r.json()
    ack = d.get("ack") or {}
    return {"ok": bool(d.get("ok")), "filled": float(ack.get("fill_count") or 0),
            "avg": ack.get("average_fill_price"), "uuid": d.get("uuid"), "err": d.get("error")}


def main():
    global session_pnl
    log(f"SCALP start | entry<=60c drift>={DRIFT_MIN}% exit@+{SCALP_C}c floor=${CASH_FLOOR} poll={POLL}s")
    s = httpx.get(f"{MC}/api/stats", timeout=10).json()
    assert s.get("keys") and not s.get("kill"), "MC not armed"
    log("MC armed; speed run live")
    with httpx.Client(headers={"Accept-Encoding": "identity"}) as cx:
        while True:
            if session_pnl * 100 <= SESSION_STOP:
                log(f"SESSION STOP {session_pnl:+.2f}$")
                return
            try:
                held = positions()
            except Exception:
                held = {}
            # ---- EXITS ----
            for t, pos in held.items():
                try:
                    b = book(cx, t)
                except Exception:
                    continue
                if b["status"] != "active":
                    continue
                bid = round(b["yb"])
                if bid >= pos["entry_c"] + SCALP_C and 1 <= bid <= 99:
                    sell_px = 100 - bid  # MC maps side=no price P -> ask@(100-P); ask@bid => P=100-bid
                    r = fire(t, "no", sell_px, int(pos["fp"]))
                    if r["ok"] and r["filled"] > 0:
                        profit = (bid - pos["entry_c"]) * pos["fp"] / 100.0
                        session_pnl += profit
                        log(f"SCALP-OUT {t[:38]} sold x{pos['fp']:g} @ {bid}c (entry {pos['entry_c']}c) "
                            f"+${profit:.2f} | session ${session_pnl:+.2f}")
                    elif r["ok"]:
                        log(f"exit resting {t[:30]} @ {bid}c")
                    time.sleep(0.25)
            # ---- ENTRIES ----
            if len(held) < MAX_OPEN:
                c = cash()
                if c and c < CASH_FLOOR:
                    log(f"cash ${c:.2f} < floor — entries paused")
                    time.sleep(POLL * 6)
                    continue
                for series, pair in SERIES:
                    if any(t.startswith(series) for t in held):
                        continue
                    try:
                        m = window_market(cx, series)
                        if not m:
                            continue
                        d = drift(cx, pair)
                        if d >= DRIFT_MIN and m["ya"] <= ENTRY_MAX:
                            side, price = "yes", m["ya"]
                        elif d <= -DRIFT_MIN and (100 - m["yb"]) <= ENTRY_MAX:
                            side, price = "no", 100 - m["yb"]
                        else:
                            continue
                        r = fire(m["ticker"], side, price, 1)
                        if r["ok"] and r["filled"] > 0:
                            log(f"ENTRY {side.upper()} x1 @ {price}c {series} drift {d:+.2f}% ttl {m['ttl']:.0f}s | FILLED avg={r['avg']}")
                        elif r["ok"]:
                            log(f"entry resting {series} {side} {price}c")
                        else:
                            log(f"entry rejected {series}: {str(r['err'])[:60]}")
                        time.sleep(0.3)
                    except Exception as e:
                        log(f"entry warn {series}: {repr(e)[:60]}")
            time.sleep(POLL)


if __name__ == "__main__":
    sys.exit(main())
