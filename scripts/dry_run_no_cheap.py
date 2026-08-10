"""dry_run_no_cheap.py — paper lane: NO entries only when drift<0 and price<=35c.

Spawn with:
  .venv311/Scripts/pythonw.exe scripts/dry_run_no_cheap.py \
    --lane dry-no-cheap-1 --clip 1 --minutes 120
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import fleetlib
import sb

parser = argparse.ArgumentParser()
parser.add_argument('--lane', required=True)
parser.add_argument('--clip', type=int, default=1)
parser.add_argument('--minutes', type=int, default=120)
args = parser.parse_args()

LANE = args.lane
CLIP_USD = args.clip
MINUTES = args.minutes
POLL = 30
ENTRY_MAX = 35      # cheap NO only
DRIFT_MIN = 0.20
TTL_MIN = 540

ROOT = sb.Path(__file__).parent
MC = "http://127.0.0.1:8420"
DRIFT_PAIR = {
    "KXBTC": "XBTUSD", "KXETH": "ETHUSD", "KXSOL": "SOLUSD",
    "KXXRP": "XRPUSD", "KXDOGE": "DOGEUSD",
}
SERIES = ["KXBTC", "KXETH", "KXSOL", "KXXRP", "KXDOGE"]

state = {
    "start_ts": time.time(), "minutes": MINUTES, "clip_usd": CLIP_USD,
    "entries": 0, "wins": 0, "losses": 0, "scalps": 0, "settles": 0,
    "realized": 0.0, "equity": float(CLIP_USD * 100),
    "open": 0, "maxDD": 0.0, "net": 0.0,
}
open_pos = {}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def publish():
    fleetlib.acquire_lock("dry")
    try:
        con = sb.sb_conn()
        cur = con.cursor()
        cur.execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES (%s, %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=EXCLUDED.updated_at",
            (f"dry_run_state:{LANE}", json.dumps(state)),
        )
        con.commit()
        con.close()
    finally:
        fleetlib.checkin("dry")


def book(ticker):
    try:
        import httpx
        r = httpx.get(f"https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}", timeout=10)
        m = r.json().get("market") or {}
        return {
            "ya": float(m.get("yes_ask_dollars") or 0) * 100,
            "yb": float(m.get("yes_bid_dollars") or 0) * 100,
            "status": m.get("status"),
        }
    except Exception:
        return {"ya": 0, "yb": 0, "status": "unknown"}


def drift(pair):
    try:
        import httpx
        d = httpx.get(f"https://api.kraken.com/0/public/Ticker?pair={pair}", timeout=10).json()["result"]
        k = next(iter(d))
        return (float(d[k]["c"][0]) - float(d[k]["o"][0])) / float(d[k]["o"][0]) * 100
    except Exception:
        return 0.0


def fire(ticker, side, price, count=1):
    try:
        import httpx
        r = httpx.post(
            f"{MC}/api/order",
            json={"ticker": ticker, "side": side, "price": int(price), "count": count, "mode": "paper", "confirm": "dry"},
            timeout=10,
        )
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def settle(ticker, entry_p, fp):
    b = book(ticker)
    if b["status"] != "active":
        return 0.0
    bid = b["yb"]
    if entry_p <= 50:
        pnl = (bid - entry_p) * fp / 100.0
    else:
        pnl = (entry_p - bid) * fp / 100.0
    return pnl


log(f"dry-no-cheap start | clip=${CLIP_USD} max_price={ENTRY_MAX}c drift<={-DRIFT_MIN}% poll={POLL}s")
publish()
dead_for = 0
while dead_for < 3 and time.time() - state["start_ts"] < MINUTES * 60:
    try:
        # exits
        for t, pos in list(open_pos.items()):
            b = book(t)
            if b["status"] != "active":
                pnl = settle(t, pos["entry"], pos["fp"])
                state["realized"] += pnl
                state["equity"] += pnl * 100
                state["net"] += pnl
                if pnl > 0:
                    state["wins"] += 1
                else:
                    state["losses"] += 1
                state["settles"] += 1
                del open_pos[t]
                log(f"SETTLE {t} {pos['side']}@{pos['entry']}c -> {'YES' if pos['entry']<=50 else 'NO'} {'WIN' if pnl>0 else 'LOSS'} ${pnl:+.2f}")
                continue
            bid = b["yb"]
            entry = pos["entry"]
            if pos["side"] == "no":
                if bid <= entry - 15:
                    pnl = (entry - bid) * pos["fp"] / 100.0
                    state["realized"] += pnl
                    state["equity"] += pnl * 100
                    state["net"] += pnl
                    state["scalps"] += 1
                    if pnl > 0:
                        state["wins"] += 1
                    else:
                        state["losses"] += 1
                    log(f"SCALP-OUT {t} NO covered x{pos['fp']} @ {bid}c (entry {entry}c) ${pnl:+.2f}")
                    del open_pos[t]
                elif bid >= entry + 10:
                    pnl = (entry - bid) * pos["fp"] / 100.0
                    state["realized"] += pnl
                    state["equity"] += pnl * 100
                    state["net"] += pnl
                    state["losses"] += 1
                    log(f"STOP-OUT {t} NO covered x{pos['fp']} @ {bid}c (entry {entry}c) ${pnl:+.2f}")
                    del open_pos[t]

        # entries: NO only, cheap
        if len(open_pos) < 3:
            for s in SERIES:
                if any(t.startswith(s) for t in open_pos):
                    continue
                mkt = f"{s}-26AUG061715-15"
                b = book(mkt)
                if b["status"] != "active":
                    continue
                no_p = 100 - b["yb"]
                if no_p > ENTRY_MAX or no_p < 1:
                    continue
                d = drift(DRIFT_PAIR[s])
                if d >= -DRIFT_MIN:
                    continue
                r = fire(mkt, "no", no_p, CLIP_USD)
                if r.get("ok"):
                    open_pos[mkt] = {"side": "no", "entry": no_p, "fp": CLIP_USD}
                    state["entries"] += 1
                    state["open"] = len(open_pos)
                    log(f"ENTRY NO x{CLIP_USD} @ {no_p}c {mkt} drift {d:+.2f}%")
                break
        state["open"] = len(open_pos)
        dd = state["equity"] - float(CLIP_USD * 100)
        if dd < state["maxDD"]:
            state["maxDD"] = dd
        publish()
        dead_for = 0
    except Exception as e:
        dead_for += 1
        log(f"ERR {e}")
    time.sleep(POLL)

log(f"dry-no-cheap done | net=${state['net']:+.2f} W={state['wins']} L={state['losses']} entries={state['entries']}")
publish()
