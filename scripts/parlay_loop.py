# file_id: SOM-PY-0952-v1.0.0 name: parlay_loop.py description: Parlay loop — fixed-% bankroll allocation fanned wide across all Kalshi combo families (2-10c tails), profits loop back to cash and compound; caps + kill-switch + lock; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [parlay, loop, compounding, mve, combos, live] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""parlay_loop.py — fan it out wide, loop the profits back.

Every CYCLE_S: allocation = ALLOC_PCT of cash (bounded MIN/MAX_CYCLE).
Buy 1-contract tickets across the WIDEST spread of open combo markets
priced 2-10c (all families: multigame, cross-category, crypto targets),
highest volume first, never the same market twice while held.
Settles auto-pay to cash -> next cycle's allocation grows (compound).
Caps: MAX_EXPOSED_PCT of equity outstanding; daily cap DAILY_CAP_PCT;
MC kill switch honored; lock 'parlay'; runlog-narrated.
"""
from __future__ import annotations

import base64
import hashlib
import os
import sys
import time
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

CYCLE_S = 600
ALLOC_PCT = 0.10         # 10% of cash per cycle (wary mode)
MIN_CYCLE, MAX_CYCLE = 2.00, 20.00
PRICE_LO, PRICE_HI = 2, 10
MAX_EXPOSED_PCT = 0.25    # stop buying when open-parlay cost > 25% of equity
DAILY_CAP_PCT = 0.35      # stop when today's parlay spend > 35% of equity
EQUITY_FLOOR = 60.00      # never trade below this equity (the vault line)

today = time.strftime("%Y-%m-%d")
spent_today = 0.0


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)
    runlog.log_event("parlay", m)


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


def account():
    b = kget("/portfolio/balance")
    return float(b.get("balance_dollars") or 0), (b.get("portfolio_value") or 0) / 100


def open_combo_cost():
    cost = 0.0
    held = set()
    pos = kget("/portfolio/positions?limit=200")
    for mp in pos.get("market_positions", []):
        t = mp.get("ticker", "")
        if "KXMV" not in t:
            continue
        fp = float(mp.get("position_fp") or 0)
        if fp > 0:
            cost += float(mp.get("total_traded_dollars") or 0)
            held.add(t)
    return cost, held


def fire(ticker, price, count=1):
    try:
        r = httpx.post(f"{MC}/api/order", json={"ticker": ticker, "side": "yes", "price": price,
                       "count": count, "mode": "live", "passkey": PK, "confirm": "FIRE"}, timeout=30)
        d = r.json()
        ack = d.get("ack") or {}
        return {"ok": bool(d.get("ok")), "filled": float(ack.get("fill_count") or 0)}
    except Exception:
        return {"ok": False, "filled": 0.0}


def candidates(cx, held):
    r = cx.get(f"{KALSHI}/markets", params={"limit": 1000, "status": "open"}, timeout=30)
    out = []
    for m in r.json().get("markets", []):
        t = m.get("ticker", "")
        if "KXMV" not in t or t in held:
            continue
        try:
            ya = round(float(m.get("yes_ask_dollars") or 0) * 100)
            vol = float(m.get("volume_fp") or 0)
        except Exception:
            continue
        if PRICE_LO <= ya <= PRICE_HI:
            out.append((vol, t, ya))
    out.sort(key=lambda x: -x[0])
    return out


def main():
    global spent_today, today
    fleetlib.acquire_lock("parlay")
    log(f"parlay_loop start | {ALLOC_PCT:.0%}/cycle min ${MIN_CYCLE} max ${MAX_CYCLE} "
        f"| band {PRICE_LO}-{PRICE_HI}c | caps {MAX_EXPOSED_PCT:.0%} exposed / {DAILY_CAP_PCT:.0%} daily | floor ${EQUITY_FLOOR}")
    with httpx.Client(headers={"Accept-Encoding": "identity"}, timeout=30) as cx:
        while True:
            fleetlib.checkin("parlay")
            try:
                if time.strftime("%Y-%m-%d") != today:
                    today = time.strftime("%Y-%m-%d")
                    spent_today = 0.0
                cash, pv = account()
                equity = cash + pv
                if equity < EQUITY_FLOOR or cash < MIN_CYCLE:
                    log(f"below floor: equity ${equity:.2f} cash ${cash:.2f} — idle")
                    for _ in range(max(1, CYCLE_S // 30)):
                        fleetlib.checkin("parlay")
                        time.sleep(30)
                    continue
                if spent_today > DAILY_CAP_PCT * equity:
                    log(f"daily cap reached (${spent_today:.2f}) — idle")
                    for _ in range(max(1, CYCLE_S // 30)):
                        fleetlib.checkin("parlay")
                        time.sleep(30)
                    continue
                exposed, held = open_combo_cost()
                if exposed > MAX_EXPOSED_PCT * equity:
                    log(f"exposure cap: open ${exposed:.2f} > {MAX_EXPOSED_PCT:.0%} of ${equity:.2f} — idle")
                    for _ in range(max(1, CYCLE_S // 30)):
                        fleetlib.checkin("parlay")
                        time.sleep(30)
                    continue
                alloc = min(MAX_CYCLE, max(MIN_CYCLE, ALLOC_PCT * cash))
                cands = candidates(cx, held)
                spent = 0.0
                bought = 0
                for vol, t, px in cands:
                    if spent + px / 100 > alloc:
                        break
                    r = fire(t, px)
                    if r["ok"] and r["filled"] > 0:
                        spent += px / 100
                        bought += 1
                        runlog.assert_event(True, "parlay", f"ticket {t[:40]} @{px}c", ticker=t)
                    time.sleep(0.35)
                spent_today += spent
                log(f"cycle: +{bought} tickets ${spent:.2f} | day ${spent_today:.2f} | equity ${equity:.2f} exposed ${exposed:.2f}")
            except Exception as e:
                log(f"cycle warn {repr(e)[:60]}")
            # chunked sleep: checkin every 30s so liveness heartbeats stay fresh
            for _ in range(max(1, CYCLE_S // 30)):
                fleetlib.checkin("parlay")
                time.sleep(30)


if __name__ == "__main__":
    sys.exit(main())
