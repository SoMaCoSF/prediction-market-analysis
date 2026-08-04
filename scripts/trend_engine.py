# file_id: SOM-PY-0965-v1.0.0 name: trend_engine.py description: Parameterized 15M trend engine — one script, any series: argv = SERIES KRAKEN_PAIR; Kraken-proven drift signal + tape momentum, both-side exits, own lock; the fan-out lane project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [trend, fanout, parameterized, crypto, live] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""trend_engine.py — the fan-out lane. Usage: trend_engine.py KXETH15M ETHUSD
Same proven rules as btc_trend: tape momentum w/ Kraken drift fallback,
early-window trend entries, +15/-10 exits, floor, session stop, own lock.
"""
from __future__ import annotations

import base64
import hashlib
import json
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
SERIES = sys.argv[1] if len(sys.argv) > 1 else "KXBTC15M"
PAIR = sys.argv[2] if len(sys.argv) > 2 else "XBTUSD"
SYM = SERIES.replace("KX", "").replace("15M", "")
LANE = f"trend-{SYM.lower()}"
MC = os.getenv("MC_URL", "http://127.0.0.1:8420")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
PK = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()
STREAM = ROOT / "data" / "uuid_stream.db"

MOM_BPS, MOM2_BPS = 3.0, 6.0
ENTRY_MIN, ENTRY_MAX, TTL_MIN = 25, 60, 480
TAKE, STOP = 15, 10
FLOOR, SESSION_STOP, POLL = 2.50, -300, 5   # FLOOR = fallback when vault state missing/stale (grind mode: 2.50)

# promoter handoff: data/engine_params.json {"take","stop","source","n","ts"}
PARAMS_FILE = ROOT / "data" / "engine_params.json"


def governor_ok():
    """Circuit breaker: entries blocked when governor is HALT/STOP. Exits never blocked."""
    try:
        con = sb.sb_conn()
        cur = con.cursor()
        cur.execute("SELECT v FROM mc_state WHERE k='governor:state'")
        row = cur.fetchone()
        con.close()
        if not row:
            return True
        return json.loads(row[0]).get("state") == "NORMAL"
    except Exception:
        return True
_start_ts = time.time()        # this process's own start time
_params_ts = _start_ts         # only adopt params FRESHER than this watermark


def adopt_params() -> bool:
    """Adopt TAKE/STOP from the promoter's engine_params.json.

    Fires at startup and every 50 cycles. Only fresher-than-watermark files
    count (watermark starts at this engine's own start time, then advances to
    the adopted file's ts), so a stale file is never re-adopted twice.
    """
    global TAKE, STOP, _params_ts
    try:
        if not PARAMS_FILE.exists():
            return False
        d = json.loads(PARAMS_FILE.read_text(encoding="utf-8"))
        ts = float(d.get("ts") or PARAMS_FILE.stat().st_mtime)
        if ts <= _params_ts:
            return False
        take, stop = int(d["take"]), int(d["stop"])
        if not (1 <= take <= 99 and 1 <= stop <= 99):
            return False
        TAKE, STOP = take, stop
        _params_ts = ts
        log(f"ADOPT engine_params take+{TAKE} stop-{STOP} from {d.get('source')} "
            f"n={d.get('n')} exp=${float(d.get('expectancy_usd') or 0):+.3f}")
        return True
    except Exception as e:
        log(f"params adopt warn {repr(e)[:60]}")
        return False

session_pnl = 0.0
positions: list[dict] = []   # concurrent horizontal positions (max MAX_CONC)
MAX_CONC = 2

_floor_cache = {"v": FLOOR, "ts": 0.0}


def cash_floor() -> float:
    """Cash floor = vault reserve (mc_state vault:state), cached 30s.

    Falls back to the hardcoded FLOOR when vault state is missing or
    stale (>300s — vault daemon dead -> conservative $20 line)."""
    if time.time() - _floor_cache["ts"] > 30:
        try:
            con = sb.sb_conn()
            cur = con.cursor()
            cur.execute("SELECT v FROM mc_state WHERE k='vault:state'")
            row = cur.fetchone()
            con.close()
            val = FLOOR
            if row:
                st = json.loads(row[0])
                if time.time() - float(st.get("ts") or 0) <= 300:
                    val = float(st.get("reserve") or FLOOR)
            _floor_cache["v"] = val
        except Exception:
            pass
        _floor_cache["ts"] = time.time()
    return _floor_cache["v"]


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] [{LANE}] {m}", flush=True)
    runlog.log_event(LANE, m)


def tape_mom():
    """3-min momentum: RAM tick service first (sub-ms), sqlite tape fallback."""
    try:
        r = httpx.get(f"http://127.0.0.1:8421/tick/{SYM}?secs=180", timeout=1.5)
        d = r.json()
        if d.get("n", 0) >= 10 and d.get("age_ms", 9999) < 5000:
            return float(d["mom_bps"])
    except Exception:
        pass
    try:
        con = sqlite3.connect(STREAM)
        rows = con.execute("SELECT ts, price_c FROM stream WHERE source IN ('kalshi-ws','spot') AND symbol=? AND ts > ? ORDER BY ts",
                           (SYM, int(time.time()) - 200)).fetchall()
        con.close()
        if len(rows) < 10:
            return None
        return (rows[-1][1] - rows[0][1]) / rows[0][1] * 10000.0
    except Exception:
        return None


def kraken_mom(cx):
    try:
        d = cx.get(f"https://api.kraken.com/0/public/Ticker?pair={PAIR}", timeout=10).json()["result"]
        k = next(iter(d))
        return (float(d[k]["c"][0]) - float(d[k]["o"])) / float(d[k]["o"]) * 100 * 40.0
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
        return {"ok": bool(d.get("ok")), "filled": float((d.get("ack") or {}).get("fill_count") or 0)}
    except Exception:
        return {"ok": False, "filled": 0.0}


def book(cx, ticker):
    m = cx.get(f"{KALSHI}/markets/{ticker}", timeout=15).json().get("market", {})
    return {"ya": float(m.get("yes_ask_dollars") or 0) * 100,
            "yb": float(m.get("yes_bid_dollars") or 0) * 100,
            "result": (m.get("result") or "").lower()}


def window(cx):
    r = cx.get(f"{KALSHI}/markets", params={"limit": 5, "status": "open", "series_ticker": SERIES}, timeout=15)
    for m in r.json().get("markets", []):
        ya = float(m.get("yes_ask_dollars") or 0)
        if not (0 < ya < 1):
            continue
        close = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
        if close - time.time() >= TTL_MIN:
            return {"ticker": m["ticker"], "ya": round(ya * 100), "yb": round(float(m.get("yes_bid_dollars") or 0) * 100),
                    "ttl": close - time.time(), "close": close}
    return None


def main():
    global session_pnl
    fleetlib.acquire_lock(LANE)
    adopt_params()   # promoter handoff at startup (only if fresher than our start)
    log(f"start | {SERIES}/{PAIR} mom>={MOM_BPS}bps take+{TAKE} stop-{STOP} floor=vault:state reserve (fallback ${FLOOR})")
    cycle = 0
    with httpx.Client(headers={"Accept-Encoding": "identity"}) as cx:
        while True:
            fleetlib.checkin(LANE)
            cycle += 1
            if cycle % 50 == 0:
                adopt_params()   # promoter handoff mid-run
            try:
                if session_pnl * 100 <= SESSION_STOP:
                    log(f"SESSION STOP ${session_pnl:+.2f}")
                    return
                for pos in list(positions):
                    b = book(cx, pos["ticker"])
                    if b["result"] in ("yes", "no"):
                        won = b["result"] == pos["side"]
                        pnl = (100 - pos["entry_c"]) if won else -pos["entry_c"]
                        session_pnl += pnl / 100.0 * pos.get("qty", 1)
                        log(f"SETTLED {pos['side']}@{pos['entry_c']}c -> {b['result']} {'WIN' if won else 'LOSS'} | session ${session_pnl:+.2f}")
                        positions.remove(pos)
                    else:
                        bid = round(b["yb"]) if pos["side"] == "yes" else round(100 - b["ya"])
                        if bid >= pos["entry_c"] + TAKE or bid <= pos["entry_c"] - STOP:
                            sell_px = 100 - bid if pos["side"] == "yes" else bid
                            r = fire(pos["ticker"], "no" if pos["side"] == "yes" else "yes", sell_px, pos.get("qty", 1))
                            if r["ok"] and r["filled"] > 0:
                                pnl = (bid - pos["entry_c"]) * pos.get("qty", 1)
                                session_pnl += pnl / 100.0
                                log(f"{'TAKE' if pnl > 0 else 'STOP'}-OUT @{bid}c (in {pos['entry_c']}c) {pnl:+}c | session ${session_pnl:+.2f}")
                                positions.remove(pos)
                if len(positions) < MAX_CONC:
                    c = cash()
                    if c and c < cash_floor():
                        time.sleep(POLL * 6)
                        continue
                    if not governor_ok():
                        time.sleep(POLL * 6)
                        continue
                    mom = tape_mom()
                    if mom is None:
                        mom = kraken_mom(cx)
                    m = window(cx)
                    if m and mom is not None and abs(mom) >= MOM_BPS:
                        if mom > 0 and ENTRY_MIN <= m["ya"] <= ENTRY_MAX:
                            side, price = "yes", m["ya"]
                        elif mom < 0 and ENTRY_MIN <= (100 - m["yb"]) <= ENTRY_MAX:
                            side, price = "no", 100 - m["yb"]
                        else:
                            side = None
                        if side:
                            # equity ladder: base size follows the bankroll, strong signal doubles
                            base = 2 if (c or 0) >= 25 else 1
                            qty = min(4, base * (2 if abs(mom) >= MOM2_BPS else 1))
                            r = fire(m["ticker"], side, price, qty)
                            if r["ok"] and r["filled"] > 0:
                                positions.append({"ticker": m["ticker"], "side": side, "entry_c": price, "close": m["close"], "qty": qty})
                                log(f"ENTRY {side.upper()} x{qty} @ {price}c mom {mom:+.1f}bps | FILLED ({len(positions)}/{MAX_CONC})")
            except Exception as e:
                log(f"cycle warn {repr(e)[:60]}")
            time.sleep(POLL)


if __name__ == "__main__":
    sys.exit(main())
