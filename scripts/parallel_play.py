# file_id: SOM-PY-0932-v1.0.0 name: parallel_play.py description: $10 parallel volatile play — momentum sleeve (crypto 15M by 24h drift) + longshot lottery basket + LAD add, all verified against exchange acks project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [play, parallel, volatile, kalshi, live] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""parallel_play.py — fire the $10 basket through mission control, verify each ack."""
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

def market(cx, ticker_or_series, series=True):
    params = {"limit": 5, "status": "open"}
    params["series_ticker" if series else "ticker"] = ticker_or_series
    r = cx.get(f"{KALSHI}/markets", params=params, timeout=15)
    ms = r.json().get("markets", [])
    if not ms:
        return None
    m = ms[0]
    ya = float(m.get("yes_ask_dollars") or 0)
    yb = float(m.get("yes_bid_dollars") or 0)
    return {"ticker": m["ticker"], "yes_ask": round(ya * 100), "yes_bid": round(yb * 100),
            "close": m.get("close_time", "")}

def drift24(cx, sym):
    try:
        d = cx.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={sym}USDT", timeout=8).json()
        return float(d["priceChangePercent"])
    except Exception:
        return 0.0

def fire(cx, ticker, side, price, count=1):
    r = httpx.post(f"{MC}/api/order", json={
        "ticker": ticker, "side": side, "price": price, "count": count,
        "mode": "live", "passkey": PK, "confirm": "FIRE"}, timeout=30)
    d = r.json()
    ack = d.get("ack") or {}
    filled = float(ack.get("fill_count") or 0)
    cost = price * count if filled > 0 else 0
    return {"ok": bool(d.get("ok")), "filled": filled, "status": r.status_code,
            "uuid": d.get("uuid"), "coi": d.get("client_order_id"), "cost": cost,
            "avg": ack.get("average_fill_price"), "err": d.get("error")}

def main():
    spent = 0
    plays = []
    with httpx.Client(headers={"Accept-Encoding": "identity"}) as cx:
        # ---- sleeve 1: crypto 15M momentum by 24h drift (BTC excluded - bot owns it) ----
        print("=== SLEEVE 1: crypto 15M momentum ===")
        for series, sym in [("KXETH15M", "ETH"), ("KXSOL15M", "SOL"), ("KXXRP15M", "XRP"), ("KXDOGE15M", "DOGE")]:
            m = market(cx, series)
            if not m:
                print(f"  {series}: no open market")
                continue
            d = drift24(cx, sym)
            if d >= 0.3 and m["yes_ask"] <= 60:
                side, price = "yes", m["yes_ask"]
            elif d <= -0.3 and (100 - m["yes_bid"]) <= 60:
                side, price = "no", 100 - m["yes_bid"]
            else:
                print(f"  {series}: drift {d:+.2f}% — no clear read, skip")
                continue
            if spent + price > BUDGET_CENTS:
                print(f"  {series}: budget reached, skip")
                continue
            r = fire(cx, m["ticker"], side, price)
            spent += r["cost"]
            plays.append((m["ticker"], side, price, r))
            print(f"  {sym} drift {d:+.2f}% -> {side.upper()} {price}c {m['ticker'][:38]} | "
                  f"{'FILL '+str(r['filled']) if r['filled'] else ('RESTING' if r['ok'] else 'REJ '+str(r['err'])[:60])} avg={r['avg']}")
            time.sleep(0.4)

        # ---- sleeve 2: longshot lottery basket (labeled -EV, tiny) ----
        print("=== SLEEVE 2: longshot lottery (-EV, variance play) ===")
        for ticker, maxp in [("KXMLB-26-MIL", 10), ("KXMLB-26-BOS", 7), ("KXMLB-26-SEA", 4),
                             ("KXMLB-26-CWS", 3), ("KXNBA-27-MIA", 6), ("KXNBA-27-GSW", 3)]:
            m = market(cx, ticker, series=True)
            if not m or not (1 <= m["yes_ask"] <= maxp):
                print(f"  {ticker}: no book in range")
                continue
            if spent + m["yes_ask"] > BUDGET_CENTS:
                print(f"  {ticker}: budget reached, skip")
                continue
            r = fire(cx, m["ticker"], "yes", m["yes_ask"])
            spent += r["cost"]
            plays.append((m["ticker"], "yes", m["yes_ask"], r))
            print(f"  lotto YES {m['yes_ask']}c {ticker} | {'FILL '+str(r['filled']) if r['filled'] else ('RESTING' if r['ok'] else 'REJ '+str(r['err'])[:60])}")
            time.sleep(0.4)

        # ---- sleeve 3: LAD add (liquid mid) ----
        print("=== SLEEVE 3: LAD add ===")
        m = market(cx, "KXMLB-26-LAD", series=True)
        if m and spent + 2 * m["yes_ask"] <= BUDGET_CENTS:
            r = fire(cx, m["ticker"], "yes", m["yes_ask"], count=2)
            spent += r["cost"]
            plays.append((m["ticker"], "yes", m["yes_ask"], r))
            print(f"  LAD YES x2 @ {m['yes_ask']}c | {'FILL '+str(r['filled']) if r['filled'] else ('RESTING' if r['ok'] else 'REJ '+str(r['err'])[:60])}")

    print("\n=== PLAY SUMMARY ===")
    print(f"deployed: {spent}c (${spent/100:.2f}) of ${BUDGET_CENTS/100:.2f} budget across {len(plays)} orders")
    real = [p for p in plays if p[3]["filled"] > 0]
    print(f"actually filled: {len(real)}/{len(plays)}")
    for t, s, p, r in plays:
        print(f"  {t[:44]:44s} {s:3s} {p:3d}c filled={r['filled']} uuid={str(r['uuid'])[:17]} coi={r['coi']}")

if __name__ == "__main__":
    main()
