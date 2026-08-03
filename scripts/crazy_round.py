# file_id: SOM-PY-0949-v1.0.0 name: crazy_round.py description: Crazy round — immediate real-money momentum sleeve (5 crypto 15M, loose TTL) + tail basket, $4 hard cap, fill-verified project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [crazy, momentum, tails, kalshi, live] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""crazy_round.py — visible action NOW. Real orders through MC, $4 cap."""
from __future__ import annotations

import hashlib
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import httpx  # noqa: E402
import sb  # noqa: E402

MC = "http://127.0.0.1:8420"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
PK = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()
BUDGET = 400  # cents


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


def drift(cx, pair):
    d = cx.get(f"https://api.kraken.com/0/public/Ticker?pair={pair}", timeout=10).json()["result"]
    k = next(iter(d))
    return (float(d[k]["c"][0]) - float(d[k]["o"])) / float(d[k]["o"]) * 100


def main():
    spent = 0
    with httpx.Client(headers={"Accept-Encoding": "identity"}) as cx:
        print("=== MOMENTUM SLEEVE (15M, loose ttl>=300s) ===")
        for series, pair in [("KXBTC15M", "XBTUSD"), ("KXETH15M", "ETHUSD"), ("KXSOL15M", "SOLUSD"),
                             ("KXXRP15M", "XRPUSD"), ("KXDOGE15M", "DOGEUSD")]:
            try:
                r = cx.get(f"{KALSHI}/markets", params={"limit": 5, "status": "open", "series_ticker": series}, timeout=15)
                m = None
                for mm in r.json().get("markets", []):
                    ya = float(mm.get("yes_ask_dollars") or 0)
                    if not (0 < ya < 1):
                        continue
                    ttl = datetime.fromisoformat(mm["close_time"].replace("Z", "+00:00")).astimezone(timezone.utc).timestamp() - time.time()
                    if ttl >= 300:
                        m = {"ticker": mm["ticker"], "ya": round(ya * 100), "yb": round(float(mm.get("yes_bid_dollars") or 0) * 100), "ttl": ttl}
                        break
                if not m:
                    print(f"  {series}: no tradeable window")
                    continue
                d = drift(cx, pair)
                if d >= 0.15 and m["ya"] <= 70:
                    side, price = "yes", m["ya"]
                elif d <= -0.15 and (100 - m["yb"]) <= 70:
                    side, price = "no", 100 - m["yb"]
                else:
                    print(f"  {series}: drift {d:+.2f}% no read (ya={m['ya']} ttl={m['ttl']:.0f}s)")
                    continue
                if spent + price > BUDGET:
                    print(f"  {series}: budget gate")
                    continue
                res = fire(m["ticker"], side, price)
                if res["ok"] and res["filled"] > 0:
                    spent += price
                    print(f"  FILL {side.upper()} @ {price}c {series} drift {d:+.2f}% avg={res['avg']}")
                elif res["ok"]:
                    print(f"  REST {side} {price}c {series} drift {d:+.2f}%")
                else:
                    print(f"  REJ {series}: {str(res['err'])[:50]}")
                time.sleep(0.4)
            except Exception as e:
                print(f"  {series} warn {repr(e)[:50]}")

        print("=== TAIL BASKET ===")
        r = cx.get(f"{KALSHI}/markets", params={"limit": 1000, "status": "open"}, timeout=30)
        tails = []
        for mm in r.json().get("markets", []):
            try:
                ya = float(mm.get("yes_ask_dollars") or 0) * 100
            except Exception:
                continue
            if 2 <= round(ya) <= 8:
                vol = float(mm.get("volume_fp") or 0)
                tails.append((vol, mm["ticker"], round(ya), (mm.get("title") or "")[:38]))
        tails.sort(reverse=True)
        for vol, t, px, title in tails[:5]:
            if spent + px > BUDGET:
                continue
            res = fire(t, "yes", px)
            if res["ok"] and res["filled"] > 0:
                spent += px
                print(f"  FILL tail YES {px}c {t[:40]} | {title} vol={vol:.0f}")
            elif res["ok"]:
                print(f"  REST tail {px}c {t[:36]}")
            else:
                print(f"  REJ {t[:30]}")
            time.sleep(0.4)
    print(f"\n=== CRAZY ROUND: spent {spent}c (${spent/100:.2f}) of $4.00 cap ===")


if __name__ == "__main__":
    sys.exit(main())
