# file_id: SOM-PY-0938-v1.0.0 name: chaos_monkey.py description: Chaos monkey — random extreme-tail micro bets (1-5c) across all open Kalshi markets, hard $1 budget, shuffled, fill-verified project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [chaos, longshot, variance, kalshi, live, micro] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""chaos_monkey.py — flings micro bets at price tails.

Tails: YES ask in [1..5]c (long reach) or YES bid >= 95c -> NO at (100-bid) <= 5c
(extreme short reach). One contract per tail, shuffled order (the chaos), fire
through MC with ack verification. Round cap 25c every ROUND_EVERY_S; total cap
$1.00. Pure variance: most expire worthless, one 50-100x pays the batch. -EV by
design and labeled as such.
"""
from __future__ import annotations

import hashlib
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import httpx  # noqa: E402
import runlog  # noqa: E402
import sb  # noqa: E402

MC = "http://127.0.0.1:8420"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
PK = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()

TOTAL_BUDGET = 100       # cents, hard cap
ROUND_MAX = 25           # cents per round
ROUND_EVERY = 300        # seconds
BAND_LO, BAND_HI = 1, 5  # tail price band


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)
    runlog.log_event("chaos", m)


def fire(ticker, side, price):
    try:
        r = httpx.post(f"{MC}/api/order", json={"ticker": ticker, "side": side, "price": price,
                       "count": 1, "mode": "live", "passkey": PK, "confirm": "FIRE"}, timeout=30)
        d = r.json()
        ack = d.get("ack") or {}
        return {"ok": bool(d.get("ok")), "filled": float(ack.get("fill_count") or 0),
                "avg": ack.get("average_fill_price"), "uuid": d.get("uuid"), "err": d.get("error")}
    except Exception as e:
        return {"ok": False, "filled": 0.0, "avg": None, "uuid": None, "err": f"net:{repr(e)[:60]}"}


def tails(cx):
    out = []
    r = cx.get(f"{KALSHI}/markets", params={"limit": 1000, "status": "open"}, timeout=30)
    for m in r.json().get("markets", []):
        try:
            ya = float(m.get("yes_ask_dollars") or 0) * 100
            yb = float(m.get("yes_bid_dollars") or 0) * 100
        except Exception:
            continue
        t = m.get("ticker", "")
        if BAND_LO <= round(ya) <= BAND_HI:
            out.append((t, "yes", round(ya), m.get("title", "")[:40]))
        elif yb >= 95:
            no_px = 100 - round(yb)
            if BAND_LO <= no_px <= BAND_HI:
                out.append((t, "no", no_px, m.get("title", "")[:40]))
    random.shuffle(out)
    return out


def main():
    spent = 0
    log(f"chaos_monkey start | budget ${TOTAL_BUDGET/100:.2f} | band {BAND_LO}-{BAND_HI}c | round<= {ROUND_MAX}c/{ROUND_EVERY}s")
    for _ in range(10):
        try:
            s = httpx.get(f"{MC}/api/stats", timeout=10).json()
            break
        except Exception:
            time.sleep(3)
    else:
        log("MC unreachable after retries — exiting")
        return 1
    assert s.get("keys") and not s.get("kill"), "MC not armed"
    with httpx.Client(headers={"Accept-Encoding": "identity"}) as cx:
        while spent < TOTAL_BUDGET:
            round_spent = 0
            try:
                cands = tails(cx)
            except Exception as e:
                log(f"scan warn {repr(e)[:60]} — retrying")
                time.sleep(30)
                continue
            log(f"round: {len(cands)} tails in band; budget left {TOTAL_BUDGET - spent}c")
            for t, side, px, title in cands:
                if spent + px > TOTAL_BUDGET or round_spent + px > ROUND_MAX:
                    continue
                r = fire(t, side, px)
                if r["ok"]:
                    tag = "FILL" if r["filled"] else "REST"
                    spent += px if r["filled"] else 0
                    round_spent += px if r["filled"] else 0
                    log(f"  {tag} {side.upper()} {px}c {t[:44]} | {title}")
                else:
                    log(f"  REJ {t[:34]} {str(r['err'])[:40]}")
                time.sleep(0.35)
                if round_spent >= ROUND_MAX or spent >= TOTAL_BUDGET:
                    break
            log(f"round done: spent {round_spent}c | total {spent}/{TOTAL_BUDGET}c")
            runlog.assert_event(spent <= TOTAL_BUDGET, "chaos", f"budget invariant: spent {spent}c <= {TOTAL_BUDGET}c", spent=spent, cap=TOTAL_BUDGET)
            if spent >= TOTAL_BUDGET:
                break
            time.sleep(ROUND_EVERY)
    log(f"chaos budget exhausted at {spent}c — monkey sleeping. Positions ride to settlement.")


if __name__ == "__main__":
    sys.exit(main())
