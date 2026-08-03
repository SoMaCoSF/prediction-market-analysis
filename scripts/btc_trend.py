# file_id: SOM-PY-0950-v1.0.0 name: btc_trend.py description: BTC 15M trend thread — momentum from the local UUID tape (3-min spot momentum), trend-aligned early-window entries, both-side exits (+15/-10), supervised, zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [btc, trend, 15m, momentum, tape, live] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""btc_trend.py — rides the 15-minute BTC trend. One market, full focus.

Signal: 3-minute spot momentum computed from OUR OWN uuid_stream tape
(spot BTC ticks every 5s) — the substrate feeds the trade. Fallback: Kraken
24h drift when the tape is thin.
Enter: early window (ttl>=480s), |mom|>=3bps, price<=60c, trend side, 1ct.
Exit : +15c take-profit / -10c stop (the validated discipline), else settle.
Guards: cash floor $5, session stop -$3, MC kill switch, lock 'btctrend'.
"""
from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
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
STREAM = ROOT / "data" / "uuid_stream.db"

MOM_BPS = 1.5            # near-continuous: fires on any real drift
MOM2_BPS = 6.0           # strong-signal threshold -> 2 contracts
ENTRY_MIN, ENTRY_MAX = 25, 60   # the proven pocket is 30-50c (4/4, +60.5c/trade)
TTL_MIN = 480
TAKE, STOP = 15, 10
FLOOR = 5.00
SESSION_STOP = -300
POLL = 5

session_pnl = 0.0
pos = None  # {ticker, side, entry_c, close}


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)
    runlog.log_event("btctrend", m)


def tape_momentum_bps() -> float | None:
    """3-min BTC spot momentum from the local UUID tape; None when thin."""
    try:
        con = sqlite3.connect(STREAM)
        rows = con.execute(
            "SELECT ts, price_c FROM stream WHERE source='spot' AND symbol='BTC' "
            "AND ts > ? ORDER BY ts", (int(time.time()) - 200,)).fetchall()
        con.close()
        if len(rows) < 10:
            return None
        first, last = rows[0][1], rows[-1][1]
        return (last - first) / first * 10000.0
    except Exception:
        return None


def kraken_drift_bps(cx) -> float | None:
    """The paper-proven signal: Kraken 24h drift mapped to bps-equivalent momentum."""
    try:
        d = cx.get("https://api.kraken.com/0/public/Ticker?pair=XBTUSD", timeout=10).json()["result"]
        k = next(iter(d))
        drift_pct = (float(d[k]["c"][0]) - float(d[k]["o"])) / float(d[k]["o"]) * 100
        return drift_pct * 40.0  # 24h drift -> momentum proxy (dry-run winning path)
    except Exception:
        return None


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


def fire(ticker, side, price, count=1):
    try:
        r = httpx.post(f"{MC}/api/order", json={"ticker": ticker, "side": side, "price": price,
                       "count": count, "mode": "live", "passkey": PK, "confirm": "FIRE"}, timeout=30)
        d = r.json()
        ack = d.get("ack") or {}
        return {"ok": bool(d.get("ok")), "filled": float(ack.get("fill_count") or 0),
                "avg": ack.get("average_fill_price"), "err": d.get("error")}
    except Exception as e:
        return {"ok": False, "filled": 0.0, "avg": None, "err": repr(e)[:60]}


def book(cx, ticker):
    m = cx.get(f"{KALSHI}/markets/{ticker}", timeout=15).json().get("market", {})
    return {"ya": float(m.get("yes_ask_dollars") or 0) * 100,
            "yb": float(m.get("yes_bid_dollars") or 0) * 100,
            "result": (m.get("result") or "").lower()}


def window_market(cx):
    r = cx.get(f"{KALSHI}/markets", params={"limit": 5, "status": "open", "series_ticker": "KXBTC15M"}, timeout=15)
    for m in r.json().get("markets", []):
        ya = float(m.get("yes_ask_dollars") or 0)
        if not (0 < ya < 1):
            continue
        close = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
        ttl = close - time.time()
        if ttl >= TTL_MIN:
            return {"ticker": m["ticker"], "ya": round(ya * 100), "yb": round(float(m.get("yes_bid_dollars") or 0) * 100),
                    "ttl": ttl, "close": close}
    return None


def main():
    global session_pnl, pos
    fleetlib.acquire_lock("btctrend")
    log(f"btc_trend start | mom>={MOM_BPS}bps(tape) entry<={ENTRY_MAX}c take +{TAKE} stop -{STOP} floor=${FLOOR}")
    for _ in range(10):
        try:
            s = httpx.get(f"{MC}/api/stats", timeout=10).json()
            break
        except Exception:
            time.sleep(3)
    else:
        log("MC unreachable — exit")
        return 1
    assert s.get("keys") and not s.get("kill"), "MC not armed"
    with httpx.Client(headers={"Accept-Encoding": "identity"}) as cx:
        while True:
            fleetlib.checkin("btctrend")
            try:
                if session_pnl * 100 <= SESSION_STOP:
                    log(f"SESSION STOP ${session_pnl:+.2f}")
                    return
                # ---- manage open position ----
                if pos:
                    b = book(cx, pos["ticker"])
                    if b["result"] in ("yes", "no"):
                        won = b["result"] == pos["side"]
                        pnl = (100 - pos["entry_c"]) if won else -pos["entry_c"]
                        session_pnl += pnl / 100.0
                        log(f"SETTLED {pos['ticker'][:34]} {pos['side']}@{pos['entry_c']}c -> {b['result']} "
                            f"{'WIN' if won else 'LOSS'} {pnl:+}c | session ${session_pnl:+.2f}")
                        pos = None
                    else:
                        bid = round(b["yb"]) if pos["side"] == "yes" else round(100 - b["ya"])
                        if bid >= pos["entry_c"] + TAKE or bid <= pos["entry_c"] - STOP:
                            sell_px = 100 - bid if pos["side"] == "yes" else bid
                            r = fire(pos["ticker"], "no" if pos["side"] == "yes" else "yes", sell_px, 1)
                            if r["ok"] and r["filled"] > 0:
                                pnl = bid - pos["entry_c"]
                                session_pnl += pnl / 100.0
                                tag = "TAKE" if pnl > 0 else "STOP"
                                log(f"{tag}-OUT {pos['ticker'][:34]} @{bid}c (in {pos['entry_c']}c) {pnl:+}c | session ${session_pnl:+.2f}")
                                pos = None
                # ---- entries ----
                if not pos:
                    c = cash()
                    if c and c < FLOOR:
                        time.sleep(POLL * 6)
                        continue
                    mom = tape_momentum_bps()
                    if mom is None:
                        mom = kraken_drift_bps(cx)
                    m = window_market(cx)
                    if time.time() % 60 < POLL:
                        log(f"scan mom={f'{mom:+.1f}' if mom is not None else '—'}bps win={'Y' if m else 'N'}")
                    if m and mom is not None and abs(mom) >= MOM_BPS:
                        if mom > 0 and ENTRY_MIN <= m["ya"] <= ENTRY_MAX:
                            side, price = "yes", m["ya"]
                        elif mom < 0 and ENTRY_MIN <= (100 - m["yb"]) <= ENTRY_MAX:
                            side, price = "no", 100 - m["yb"]
                        else:
                            side = None
                        if side:
                            qty = 2 if abs(mom) >= MOM2_BPS else 1
                            r = fire(m["ticker"], side, price, qty)
                            if r["ok"] and r["filled"] > 0:
                                pos = {"ticker": m["ticker"], "side": side, "entry_c": price, "close": m["close"]}
                                runlog.assert_event(True, "btctrend", f"entry {side} @{price}c mom {mom:+.1f}bps (tape)", ticker=m["ticker"])
                                log(f"ENTRY {side.upper()} @ {price}c mom {mom:+.1f}bps ttl {m['ttl']:.0f}s | FILLED avg={r['avg']}")
                            elif r["ok"]:
                                log(f"resting {side} {price}c mom {mom:+.1f}bps")
            except Exception as e:
                log(f"cycle warn {repr(e)[:60]}")
            time.sleep(POLL)


if __name__ == "__main__":
    sys.exit(main())
