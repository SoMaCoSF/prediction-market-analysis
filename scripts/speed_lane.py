# file_id: SOM-PY-0966-v1.0.0 name: speed_lane.py description: $1 speed lane — max churn: cheap momentum entries (<=12c) on 15M windows, exit at +3c or settle, fastest cycle; argv SERIES PAIR; hard $1 budget; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [speed, lane, micro, churn, live] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""speed_lane.py — a dollar, speedrun. Usage: speed_lane.py KXBTC15M XBTUSD

Cheap entries (<=12c) with drift direction, +3c take or settle, 2s cycle.
Hard $1 budget — when it's spent, the lane stops and reports the run.
Goal: maximum trades/dollar — the churn experiment. runlog-narrated.
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
import fleetlib  # noqa: E402
import httpx  # noqa: E402
import runlog  # noqa: E402
import sb  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
SERIES = sys.argv[1] if len(sys.argv) > 1 else "KXBTC15M"
PAIR = sys.argv[2] if len(sys.argv) > 2 else "XBTUSD"
SYM = SERIES.replace("KX", "").replace("15M", "")
LANE = f"speed-{SYM.lower()}"
MC = os.getenv("MC_URL", "http://127.0.0.1:8420")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
PK = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()

BUDGET = 100          # cents — the dollar
ENTRY_MAX = 12
TAKE = 3
DRIFT_MIN = 0.10
TTL_MIN = 300
POLL = 2

spent = 0
wins = losses = trades = 0
pos = None


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] [{LANE}] {m}", flush=True)
    runlog.log_event(LANE, m)


def drift(cx):
    try:
        d = cx.get(f"https://api.kraken.com/0/public/Ticker?pair={PAIR}", timeout=10).json()["result"]
        k = next(iter(d))
        return (float(d[k]["c"][0]) - float(d[k]["o"])) / float(d[k]["o"]) * 100
    except Exception:
        return 0.0


def fire(ticker, side, price):
    try:
        r = httpx.post(f"{MC}/api/order", json={"ticker": ticker, "side": side, "price": price,
                       "count": 1, "mode": "live", "passkey": PK, "confirm": "FIRE"}, timeout=30)
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
            return {"ticker": m["ticker"], "ya": round(ya * 100), "yb": round(float(m.get("yes_bid_dollars") or 0) * 100)}
    return None


def main():
    global spent, wins, losses, trades, pos
    fleetlib.acquire_lock(LANE)
    log(f"SPEEDRUN start | ${BUDGET/100:.2f} budget entry<={ENTRY_MAX}c take+{TAKE}c poll={POLL}s")
    with httpx.Client(headers={"Accept-Encoding": "identity"}) as cx:
        while spent < BUDGET:
            fleetlib.checkin(LANE)
            try:
                if pos:
                    b = book(cx, pos["ticker"])
                    if b["result"] in ("yes", "no"):
                        won = b["result"] == pos["side"]
                        wins += 1 if won else 0
                        losses += 0 if won else 1
                        log(f"SETTLE {pos['side']}@{pos['entry_c']}c -> {b['result']} {'WIN' if won else 'LOSS'} | spent {spent}c W/L {wins}/{losses}")
                        pos = None
                    else:
                        bid = round(b["yb"]) if pos["side"] == "yes" else round(100 - b["ya"])
                        if bid >= pos["entry_c"] + TAKE:
                            sell_px = 100 - bid if pos["side"] == "yes" else bid
                            r = fire(pos["ticker"], "no" if pos["side"] == "yes" else "yes", sell_px)
                            if r["ok"] and r["filled"] > 0:
                                wins += 1
                                log(f"SPEED-OUT @{bid}c (in {pos['entry_c']}c) +{bid - pos['entry_c']}c | spent {spent}c W/L {wins}/{losses}")
                                pos = None
                elif spent + ENTRY_MAX <= BUDGET:
                    m = window(cx)
                    d = drift(cx)
                    if m and abs(d) >= DRIFT_MIN:
                        if d >= DRIFT_MIN and m["ya"] <= ENTRY_MAX:
                            side, price = "yes", m["ya"]
                        elif d <= -DRIFT_MIN and (100 - m["yb"]) <= ENTRY_MAX:
                            side, price = "no", 100 - m["yb"]
                        else:
                            side = None
                        if side:
                            r = fire(m["ticker"], side, price)
                            if r["ok"] and r["filled"] > 0:
                                spent += price
                                trades += 1
                                pos = {"ticker": m["ticker"], "side": side, "entry_c": price}
                                log(f"ENTRY {side.upper()} @{price}c drift {d:+.2f}% | trade #{trades} spent {spent}c")
            except Exception as e:
                log(f"warn {repr(e)[:50]}")
            time.sleep(POLL)
    log(f"SPEEDRUN DONE: {trades} trades, W/L {wins}/{losses}, spent {spent}c of {BUDGET}c")
    runlog.assert_event(trades > 0, LANE, f"speedrun completed {trades} trades on ${BUDGET/100:.2f}")


if __name__ == "__main__":
    sys.exit(main())
