# file_id: SOM-PY-0935-v1.0.0 name: profit_loop.py description: Autonomous profit loop — crypto 15M drift-momentum entries early-window only, parlay compounding (winners size up), settle write-back, bankroll guard project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [profit-loop, momentum, kalshi, live, compound] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""profit_loop.py — the income engine. Runs for hours.

Rules (distilled from today's 4/4 + two skipped windows):
  ENTER only EARLY in a 15-min window (ttl >= 540s) when drift >= ±0.20%
  and the binary still prices the move <= 60c. If repriced (>60c), the edge is
  gone — skip. Discipline over volume.
  PARLAY: base 1 contract; every realized win feeds the hot pool; hot pool >= 50c
  upgrades the next highest-drift entry to 2 contracts. Any loss -> back to 1.
  GUARD: cash floor $20 (stop firing below it), session stop -$3, kill switch
  honored server-side via MC. Settles written back to the UUID ledger.
"""
from __future__ import annotations

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
import uuid_ledger as L  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
MC = os.getenv("MC_URL", "http://127.0.0.1:8420")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
PK = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()

SERIES = [("KXBTC15M", "XBTUSD"), ("KXETH15M", "ETHUSD"), ("KXSOL15M", "SOLUSD"),
          ("KXXRP15M", "XRPUSD"), ("KXDOGE15M", "DOGEUSD")]
DRIFT_MIN = 0.20          # % over kraken 24h open
ENTRY_MAX = 60            # cents — only enter while mispriced
TTL_MIN = 540             # seconds left = early window (of 900)
CASH_FLOOR = 20.00        # stop firing below this
SESSION_STOP = -300       # cents
POLL = 10

entries: dict = {}        # ticker -> {side, entry, uuid, series}
session_realized = 0
hot_pool = 0
size_next = 1             # contracts for next entry (parlay)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def balance() -> float:
    import base64

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key((ROOT / ".kalshi_key.pem").read_bytes(), password=None)
    ts = str(int(time.time() * 1000))
    path = "/trade-api/v2/portfolio/balance"
    sig = base64.b64encode(key.sign(f"{ts}GET{path}".encode(),
                                    padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                                    hashes.SHA256())).decode()
    h = {"KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"), "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}
    d = httpx.get(KALSHI + "/portfolio/balance", headers=h, timeout=15).json()
    return float(d.get("balance_dollars") or 0)


def drift(cx, pair):
    d = cx.get(f"https://api.kraken.com/0/public/Ticker?pair={pair}", timeout=10).json()["result"]
    k = next(iter(d))
    return (float(d[k]["c"][0]) - float(d[k]["o"])) / float(d[k]["o"]) * 100


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


def fire(ticker, side, price, count):
    r = httpx.post(f"{MC}/api/order", json={"ticker": ticker, "side": side, "price": price,
                   "count": count, "mode": "live", "passkey": PK, "confirm": "FIRE"}, timeout=30)
    d = r.json()
    ack = d.get("ack") or {}
    return {"ok": bool(d.get("ok")), "filled": float(ack.get("fill_count") or 0),
            "avg": ack.get("average_fill_price"), "uuid": d.get("uuid"), "err": d.get("error")}


def settle_scan(cx):
    global session_realized, hot_pool, size_next
    for ticker, pos in list(entries.items()):
        try:
            m = cx.get(f"{KALSHI}/markets/{ticker}", timeout=15).json().get("market", {})
        except Exception:
            continue
        result = (m.get("result") or "").lower()
        if result not in ("yes", "no"):
            continue
        con = sb.sb_conn()
        cur = con.cursor()
        cur.execute("SELECT uuid FROM uuid_orders WHERE ticker=%s AND mode='live' ORDER BY created_at DESC LIMIT 1", (ticker,))
        row = cur.fetchone()
        if row:
            mkt = L.mint_market_uuid(ticker)
            fu = L.mint_fill(row[0], pos["entry"], 1, exchange_fill_id=f"loop:{ticker}")
            L.record_fill(cur, fu, fee_cents=2)
            L.apply_fill_to_position(cur, ticker, pos["side"], mkt, pos["entry"], 1, fu["ts"])
            L.settle(cur, ticker, mkt, 100 if result == "yes" else 0)
            con.commit()
            cur.execute("SELECT realized_pnl_cents FROM uuid_positions WHERE ticker=%s AND side=%s", (ticker, pos["side"]))
            r2 = cur.fetchone()
            pnl = r2[0] if r2 else 0
        else:
            pnl = 0
        con.close()
        session_realized += pnl
        won = result == pos["side"]
        if won:
            hot_pool += (100 - pos["entry"])
        else:
            size_next = 1
        log(f"SETTLED {ticker}: {result} vs our {pos['side']} -> {'WIN' if won else 'LOSS'} {pnl:+d}c | "
            f"session={session_realized:+d}c hot_pool={hot_pool}c")
        entries.pop(ticker, None)


def main():
    global size_next, hot_pool
    log(f"profit_loop start | drift>={DRIFT_MIN}% entry<={ENTRY_MAX}c ttl>={TTL_MIN}s floor=${CASH_FLOOR} stop={SESSION_STOP}c")
    s = httpx.get(f"{MC}/api/stats", timeout=10).json()
    assert s.get("keys") and not s.get("kill"), "MC not armed"
    log("MC armed; entering loop")
    with httpx.Client(headers={"Accept-Encoding": "identity"}) as cx:
        while True:
            if session_realized <= SESSION_STOP:
                log(f"SESSION STOP ({session_realized}c). Halting.")
                return
            try:
                settle_scan(cx)
            except Exception as e:
                log(f"settle warn {repr(e)[:80]}")
            try:
                cash = balance()
            except Exception:
                cash = None
            if cash is not None and cash < CASH_FLOOR:
                log(f"cash ${cash:.2f} below floor ${CASH_FLOOR} — holding fire")
                time.sleep(POLL * 6)
                continue
            for series, pair in SERIES:
                if any(p["series"] == series for p in entries.values()):
                    continue  # already riding this series
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
                    n = size_next
                    r = fire(m["ticker"], side, price, n)
                    if r["ok"] and r["filled"] > 0:
                        entries[m["ticker"]] = {"side": side, "entry": price, "uuid": r["uuid"], "series": series}
                        log(f"ENTRY {side.upper()} x{n} @ {price}c {series} drift {d:+.2f}% ttl {m['ttl']:.0f}s "
                            f"| FILLED avg={r['avg']} uuid={str(r['uuid'])[:13]}…")
                        if hot_pool >= 50 and size_next == 1:
                            size_next = 2
                            hot_pool -= 50
                            log("PARLAY: hot pool spent -> next entries sized x2")
                    elif r["ok"]:
                        log(f"RESTING {side} {price}c {series} (unfilled at ack)")
                    else:
                        log(f"REJECTED {series}: {str(r['err'])[:80]}")
                    time.sleep(0.3)
                except Exception as e:
                    log(f"cycle warn {series}: {repr(e)[:80]}")
            time.sleep(POLL)


if __name__ == "__main__":
    sys.exit(main())
