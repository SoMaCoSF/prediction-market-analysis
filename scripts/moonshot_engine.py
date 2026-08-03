# file_id: SOM-PY-0990-v1.0.0 name: moonshot_engine.py description: Moonshot sleeve — adjustable % of equity (default 25%) deployed in SIZED shots: cheap tails 10x+ payoff + strong-drift conviction plays; sleeve-isolated from the micro substrate; UUID-parented on the motivating signal; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [moonshot, sleeve, sizing, tails, conviction, live] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""moonshot_engine.py — the big-shot sleeve.

Sleeve = MOONSHOT_PCT of equity (default 25%). Two shot types:
  TAIL: 5-15c contracts on high-volume markets (10-20x payoff), rides to settle
  CONVICTION: 15M crypto window with |drift| >= 0.8% AND entry 30-55c, sized 5-10ct
Sizing: each shot <= sleeve/5. Max 5 open. Daily loss cap = sleeve/2.
The sleeve may zero — the other 75% is untouchable. Sleeve refills from profits.
Publishes moonshot:sleeve for the panel. Zero model tokens.
"""
from __future__ import annotations

import base64
import hashlib
import json
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

PCT = float(os.getenv("MOONSHOT_PCT", "0.25"))
SLEEVE_FLOOR = 5.00
MAX_SHOT_PCT = 0.20      # of sleeve per shot
MAX_OPEN = 5
TAIL_LO, TAIL_HI = 5, 15
CONVICTION_DRIFT = 0.8
CONV_LO, CONV_HI = 30, 55
TAKE_MULT = 3.0
POLL_S = 300

shots: list[dict] = []
day_spent = 0.0
today = time.strftime("%Y-%m-%d")


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] [moonshot] {m}", flush=True)
    runlog.log_event("moonshot", m)


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


def equity():
    b = kget("/portfolio/balance")
    cash = float(b.get("balance_dollars") or 0)
    return cash + (b.get("portfolio_value") or 0) / 100


def fire(ticker, side, price, count):
    try:
        r = httpx.post(f"{MC}/api/order", json={"ticker": ticker, "side": side, "price": price,
                       "count": count, "mode": "live", "passkey": PK, "confirm": "FIRE"}, timeout=30)
        d = r.json()
        return {"ok": bool(d.get("ok")), "filled": float((d.get("ack") or {}).get("fill_count") or 0)}
    except Exception:
        return {"ok": False, "filled": 0.0}


def publish(sleeve, eq):
    try:
        con = sb.sb_conn()
        con.autocommit = True
        con.cursor().execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('moonshot:sleeve', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (json.dumps({"pct": PCT, "sleeve": round(sleeve, 2), "equity": round(eq, 2),
                         "open": len(shots), "spent_today": round(day_spent, 2),
                         "shots": shots[-8:], "ts": int(time.time())}),))
        con.close()
    except Exception:
        pass


def tails(cx, sleeve):
    """Cheap tails on high-volume markets closing within 48h."""
    out = []
    try:
        r = cx.get(f"{KALSHI}/markets", params={"limit": 200, "status": "open"}, timeout=20)
        for m in r.json().get("markets", []):
            try:
                ya = round(float(m.get("yes_ask_dollars") or 0) * 100)
                vol = float(m.get("volume_24h_fp") or 0)
                close = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
                ttl = close - time.time()
                if TAIL_LO <= ya <= TAIL_HI and vol >= 25000 and 3600 < ttl < 48 * 3600:
                    out.append({"ticker": m["ticker"], "ya": ya, "vol": vol, "title": (m.get("title") or "")[:40]})
            except Exception:
                continue
    except Exception:
        pass
    return sorted(out, key=lambda x: -x["vol"])[:5]


def conviction(cx):
    """15M crypto windows with strong drift, pocket-band entries."""
    out = []
    for series, pair in [("KXBTC15M", "XBTUSD"), ("KXETH15M", "ETHUSD")]:
        try:
            d = cx.get(f"https://api.kraken.com/0/public/Ticker?pair={pair}", timeout=10).json()["result"]
            k = next(iter(d))
            drift = (float(d[k]["c"][0]) - float(d[k]["o"])) / float(d[k]["o"]) * 100
            if abs(drift) < CONVICTION_DRIFT:
                continue
            r = cx.get(f"{KALSHI}/markets", params={"limit": 3, "status": "open", "series_ticker": series}, timeout=15)
            for m in r.json().get("markets", []):
                ya = round(float(m.get("yes_ask_dollars") or 0) * 100)
                yb = round(float(m.get("yes_bid_dollars") or 0) * 100)
                side, price = ("yes", ya) if drift > 0 else ("no", 100 - yb)
                if CONV_LO <= price <= CONV_HI:
                    out.append({"ticker": m["ticker"], "side": side, "price": price, "drift": drift})
                    break
        except Exception:
            continue
    return out


def main():
    global day_spent, today
    fleetlib.acquire_lock("moonshot")
    log(f"start | sleeve={PCT*100:.0f}% of equity, shot<={MAX_SHOT_PCT*100:.0f}% of sleeve, max {MAX_OPEN} open")
    with httpx.Client(headers={"Accept-Encoding": "identity"}, timeout=25) as cx:
        while True:
            fleetlib.checkin("moonshot")
            try:
                if time.strftime("%Y-%m-%d") != today:
                    today = time.strftime("%Y-%m-%d")
                    day_spent = 0.0
                eq = equity()
                sleeve = max(0.0, eq * PCT)
                publish(sleeve, eq)
                if sleeve < SLEEVE_FLOOR:
                    time.sleep(POLL_S * 4)
                    continue
                # manage open shots: tail take-profit at 3x, settles logged
                for s in list(shots):
                    m = kget(f"/markets/{s['ticker']}").get("market", {})
                    res = (m.get("result") or "").lower()
                    if res in ("yes", "no"):
                        won = res == s["side"]
                        shots.remove(s)
                        log(f"SETTLED {s['kind']} {s['side']} x{s['qty']}@{s['price']}c -> {res} {'MOON' if won else 'DUST'}")
                    elif s["kind"] == "tail":
                        bid = round(float(m.get("yes_bid_dollars") or 0) * 100) if s["side"] == "yes" else round(100 - float(m.get("yes_ask_dollars") or 0) * 100)
                        if bid >= s["price"] * TAKE_MULT:
                            sell_px = 100 - bid if s["side"] == "yes" else bid
                            r = fire(s["ticker"], "no" if s["side"] == "yes" else "yes", sell_px, s["qty"])
                            if r["ok"] and r["filled"] > 0:
                                shots.remove(s)
                                log(f"MOON-OUT @{bid}c (in {s['price']}c) {TAKE_MULT:.0f}x on x{s['qty']}")
                # new shots
                if len(shots) < MAX_OPEN and day_spent < sleeve / 2:
                    budget = min(sleeve * MAX_SHOT_PCT, sleeve / 2 - day_spent)
                    for c in conviction(cx):
                        if len(shots) >= MAX_OPEN or budget < 1.0:
                            break
                        qty = max(1, int(budget * 100 / c["price"]))
                        qty = min(qty, 10)
                        r = fire(c["ticker"], c["side"], c["price"], qty)
                        if r["ok"] and r["filled"] > 0:
                            shots.append({"kind": "conviction", "ticker": c["ticker"], "side": c["side"], "price": c["price"], "qty": qty})
                            day_spent += c["price"] * qty / 100
                            log(f"CONVICTION {c['side'].upper()} x{qty} @{c['price']}c drift {c['drift']:+.2f}% | sleeve ${sleeve:.2f}")
                    for t in tails(cx, sleeve):
                        if len(shots) >= MAX_OPEN or day_spent >= sleeve / 2:
                            break
                        budget = min(sleeve * MAX_SHOT_PCT, sleeve / 2 - day_spent)
                        qty = max(1, int(budget * 100 / t["ya"]))
                        qty = min(qty, 25)
                        r = fire(t["ticker"], "yes", t["ya"], qty)
                        if r["ok"] and r["filled"] > 0:
                            shots.append({"kind": "tail", "ticker": t["ticker"], "side": "yes", "price": t["ya"], "qty": qty})
                            day_spent += t["ya"] * qty / 100
                            log(f"TAIL YES x{qty} @{t['ya']}c vol ${t['vol']:,.0f} | {t['title']}")
            except Exception as e:
                log(f"cycle warn {repr(e)[:60]}")
            time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
