# file_id: SOM-PY-0979-v1.0.0 name: calendar_engine.py description: Calendar engine — scan all Kalshi markets closing <6h with real volume, compute snapshot momentum (own 5-min price history), micro-bet the movers 1ct at a time; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [calendar, momentum, micro, live, cross-market] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""calendar_engine.py — micro across the calendar.

Every 60s: all open markets closing within 6h with 24h volume >= $50k.
The engine keeps its own rolling price snapshots; momentum = ask drift over
the last 5+ snapshots. Movers (|mom| >= 3¢) get a 1ct micro in the momentum
direction (<=60¢ entries). Caps: 4 open, $5/day. Sports + crypto + politics —
whatever the calendar is actually running. Zero model tokens.
"""
from __future__ import annotations

import base64
import hashlib
import os
import sys
import time
from collections import defaultdict, deque
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

POLL_S = 60
CLOSE_H = 6
MIN_VOL_24H = 50000.0
MOM_MIN_C = 3.0
ENTRY_MAX = 60
MAX_OPEN = 4
DAILY_CAP = 5.00

history: dict[str, deque] = defaultdict(lambda: deque(maxlen=12))
open_pos: list[dict] = []
spent_today = 0.0
today = time.strftime("%Y-%m-%d")


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] [calendar] {m}", flush=True)
    runlog.log_event("calendar", m)


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


def fire(ticker, side, price):
    try:
        r = httpx.post(f"{MC}/api/order", json={"ticker": ticker, "side": side, "price": price,
                       "count": 1, "mode": "live", "passkey": PK, "confirm": "FIRE"}, timeout=30)
        d = r.json()
        return {"ok": bool(d.get("ok")), "filled": float((d.get("ack") or {}).get("fill_count") or 0)}
    except Exception:
        return {"ok": False, "filled": 0.0}


def scan(cx):
    """All open markets closing <6h with volume >= MIN_VOL_24H."""
    out = []
    cursor = None
    for _ in range(4):
        params = {"limit": 200, "status": "open"}
        if cursor:
            params["cursor"] = cursor
        try:
            r = cx.get(f"{KALSHI}/markets", params=params, timeout=20)
            d = r.json()
        except Exception:
            break
        for m in d.get("markets", []):
            try:
                close = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
                ttl = close - time.time()
                vol = float(m.get("volume_24h_fp") or m.get("volume_24h") or 0)
                if 0 < ttl <= CLOSE_H * 3600 and vol >= MIN_VOL_24H:
                    out.append({"ticker": m["ticker"], "ttl": ttl, "vol": vol,
                                "ya": round(float(m.get("yes_ask_dollars") or 0) * 100),
                                "yb": round(float(m.get("yes_bid_dollars") or 0) * 100)})
            except Exception:
                continue
        cursor = d.get("cursor")
        if not cursor:
            break
    return out


def main():
    global spent_today, today
    fleetlib.acquire_lock("calendar")
    log(f"start | close<{CLOSE_H}h vol>=${MIN_VOL_24H:,.0f} mom>={MOM_MIN_C}c entry<={ENTRY_MAX}c cap ${DAILY_CAP}/day")
    with httpx.Client(headers={"Accept-Encoding": "identity"}, timeout=25) as cx:
        while True:
            fleetlib.checkin("calendar")
            try:
                if time.strftime("%Y-%m-%d") != today:
                    today = time.strftime("%Y-%m-%d")
                    spent_today = 0.0
                # manage open positions: settle check only (micro rides to close)
                for p in list(open_pos):
                    m = kget(f"/markets/{p['ticker']}").get("market", {})
                    res = (m.get("result") or "").lower()
                    if res in ("yes", "no"):
                        won = res == p["side"]
                        open_pos.remove(p)
                        log(f"SETTLED {p['side']}@{p['price']}c -> {res} {'WIN' if won else 'LOSS'}")
                markets = scan(cx)
                for m in markets:
                    if m["ya"] > 0:
                        history[m["ticker"]].append(m["ya"])
                for m in markets:
                    h = history[m["ticker"]]
                    if len(h) < 5 or len(open_pos) >= MAX_OPEN or spent_today >= DAILY_CAP:
                        continue
                    mom = h[-1] - h[0]
                    if abs(mom) < MOM_MIN_C:
                        continue
                    if mom > 0 and m["ya"] <= ENTRY_MAX:
                        side, price = "yes", m["ya"]
                    elif mom < 0 and (100 - m["yb"]) <= ENTRY_MAX:
                        side, price = "no", 100 - m["yb"]
                    else:
                        continue
                    r = fire(m["ticker"], side, price)
                    if r["ok"] and r["filled"] > 0:
                        open_pos.append({"ticker": m["ticker"], "side": side, "price": price})
                        spent_today += price / 100
                        log(f"MICRO {side.upper()} @{price}c mom {mom:+.0f}c vol ${m['vol']:,.0f} ttl {m['ttl']/3600:.1f}h | {m['ticker'][:34]}")
                log(f"scan: {len(markets)} closing<6h liquid | open {len(open_pos)}/{MAX_OPEN} spent ${spent_today:.2f}")
            except Exception as e:
                log(f"cycle warn {repr(e)[:60]}")
            time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
