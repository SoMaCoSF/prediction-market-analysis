# file_id: SOM-PY-0933-v1.0.0 name: parallel_play2.py description: $10 parallel play v2 — fixed feeds (Kraken drift, ticker-direct fetch), momentum + longshot + mid sleeves, every fill verified vs ack fill_count project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [play, parallel, kalshi, live, momentum] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""parallel_play2.py — the corrected $10 deployment."""
from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import httpx  # noqa: E402
import sb  # noqa: E402

MC = "http://127.0.0.1:8420"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
PK = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()
BUDGET_CENTS = 1000

def mkt_by_ticker(cx, ticker):
    r = cx.get(f"{KALSHI}/markets/{ticker}", timeout=15)
    m = r.json().get("market") or {}
    if not m.get("ticker"):
        return None
    ya = float(m.get("yes_ask_dollars") or 0)
    yb = float(m.get("yes_bid_dollars") or 0)
    return {"ticker": m["ticker"], "yes_ask": round(ya * 100), "yes_bid": round(yb * 100)}

def mkt_by_series(cx, series):
    r = cx.get(f"{KALSHI}/markets", params={"limit": 5, "status": "open", "series_ticker": series}, timeout=15)
    for m in r.json().get("markets", []):
        ya = float(m.get("yes_ask_dollars") or 0)
        if 0 < ya < 1:
            yb = float(m.get("yes_bid_dollars") or 0)
            return {"ticker": m["ticker"], "yes_ask": round(ya * 100), "yes_bid": round(yb * 100)}
    return None

def drift24_kraken(cx, pair):
    try:
        d = cx.get(f"https://api.kraken.com/0/public/Ticker?pair={pair}", timeout=10).json()
        res = d["result"]
        k = next(iter(res))
        last = float(res[k]["c"][0])
        open24 = float(res[k]["o"])
        return (last - open24) / open24 * 100.0
    except Exception as e:
        print(f"    (drift feed err {pair}: {repr(e)[:60]})")
        return None

def fire(ticker, side, price, count=1):
    r = httpx.post(f"{MC}/api/order", json={
        "ticker": ticker, "side": side, "price": price, "count": count,
        "mode": "live", "passkey": PK, "confirm": "FIRE"}, timeout=30)
    d = r.json()
    ack = d.get("ack") or {}
    filled = float(ack.get("fill_count") or 0)
    return {"ok": bool(d.get("ok")), "filled": filled, "http": r.status_code,
            "uuid": d.get("uuid"), "coi": d.get("client_order_id"),
            "avg": ack.get("average_fill_price"), "err": d.get("error"),
            "cost": (price * count) if filled > 0 else 0}

def main():
    spent = 0
    plays = []
    with httpx.Client(headers={"Accept-Encoding": "identity"}) as cx:
        print("=== SLEEVE 1: crypto 15M momentum (Kraken drift) ===")
        for series, pair in [("KXETH15M", "ETHUSD"), ("KXSOL15M", "SOLUSD"),
                             ("KXXRP15M", "XRPUSD"), ("KXDOGE15M", "DOGEUSD")]:
            m = mkt_by_series(cx, series)
            if not m:
                print(f"  {series}: no open book")
                continue
            d = drift24_kraken(cx, pair)
            if d is None:
                continue
            if d >= 0.2 and m["yes_ask"] <= 60:
                side, price = "yes", m["yes_ask"]
            elif d <= -0.2 and (100 - m["yes_bid"]) <= 60:
                side, price = "no", 100 - m["yes_bid"]
            else:
                print(f"  {series}: drift {d:+.2f}% flat — skip")
                continue
            if spent + price > BUDGET_CENTS:
                print(f"  {series}: budget gate")
                continue
            r = fire(m["ticker"], side, price)
            spent += r["cost"]
            plays.append((m["ticker"], side, price, r))
            tag = "FILL" if r["filled"] else ("RESTING" if r["ok"] else f"REJ {str(r['err'])[:50]}")
            print(f"  {pair} {d:+.2f}% -> {side.upper()} {price}c {m['ticker'][:40]} | {tag} avg={r['avg']}")
            time.sleep(0.4)

        print("=== SLEEVE 2: longshot basket (ticker-direct) ===")
        for ticker, maxp in [("KXMLB-26-MIL", 12), ("KXMLB-26-BOS", 8), ("KXMLB-26-SEA", 5),
                             ("KXMLB-26-CWS", 3), ("KXNBA-27-MIA", 8), ("KXNBA-27-GSW", 4)]:
            m = mkt_by_ticker(cx, ticker)
            if not m or not (1 <= m["yes_ask"] <= maxp):
                got = m["yes_ask"] if m else "n/a"
                print(f"  {ticker}: ask={got} outside 1..{maxp} — skip")
                continue
            if spent + m["yes_ask"] > BUDGET_CENTS:
                print(f"  {ticker}: budget gate")
                continue
            r = fire(m["ticker"], "yes", m["yes_ask"])
            spent += r["cost"]
            plays.append((m["ticker"], "yes", m["yes_ask"], r))
            tag = "FILL" if r["filled"] else ("RESTING" if r["ok"] else f"REJ {str(r['err'])[:50]}")
            print(f"  lotto YES {m['yes_ask']}c {ticker} | {tag}")
            time.sleep(0.4)

        print("=== SLEEVE 3: mid-liquid adds ===")
        for ticker, n in [("KXMLB-26-LAD", 2), ("KXMLB-26-NYY", 2)]:
            m = mkt_by_ticker(cx, ticker)
            if not m or not (1 <= m["yes_ask"] <= 60):
                print(f"  {ticker}: no suitable book")
                continue
            if spent + n * m["yes_ask"] > BUDGET_CENTS:
                print(f"  {ticker}: budget gate")
                continue
            r = fire(m["ticker"], "yes", m["yes_ask"], count=n)
            spent += r["cost"]
            plays.append((m["ticker"], "yes", m["yes_ask"], r))
            tag = "FILL" if r["filled"] else ("RESTING" if r["ok"] else f"REJ {str(r['err'])[:50]}")
            print(f"  {ticker} YES x{n} @ {m['yes_ask']}c | {tag} avg={r['avg']}")
            time.sleep(0.4)

    print("\n=== PLAY SUMMARY ===")
    real = [p for p in plays if p[3]["filled"] > 0]
    resting = [p for p in plays if p[3]["ok"] and p[3]["filled"] == 0]
    print(f"deployed (filled cost): {spent}c (${spent/100:.2f}) of $10.00")
    print(f"filled: {len(real)} | resting(unfilled): {len(resting)} | total orders: {len(plays)}")
    for t, s, p, r in plays:
        print(f"  {t[:42]:42s} {s:3s} {p:3d}c filled={r['filled']:g} avg={r['avg']} uuid={str(r['uuid'])[:17]}")

if __name__ == "__main__":
    main()
