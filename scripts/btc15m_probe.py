#!/usr/bin/env python3
"""BTC-15m market-energy probe. Read-only except it prints everything needed
to decide a live micro-bet. No orders placed by this script."""
import sys, time, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

import httpx  # noqa: E402
from mission_control import KALSHI_HOST, kalshi_keys, kalshi_sign  # noqa: E402


def auth_get(path: str, params=None):
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("GET", path, ts, kpath)
    h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}
    r = httpx.get(f"{KALSHI_HOST}{path}", params=params, headers=h, timeout=20)
    r.raise_for_status()
    return r.json()


def main():
    # ---- 1. cash ----
    bal = auth_get("/portfolio/balance")
    cash = float(bal.get("balance_dollars", 0) or 0)
    pv = float(bal.get("portfolio_value", 0) or 0)
    print(f"CASH=${cash:.4f}  portfolio_value=${pv:.2f}  (floor=$10.00 -> riskable=${max(cash-10.00,0):.2f})")

    # ---- 2. find BTC-15m open markets ----
    print("\n=== BTC-15m OPEN MARKETS ===")
    markets = []
    cursor = None
    for _ in range(3):
        params = {"limit": 100, "status": "open"}
        if cursor:
            params["cursor"] = cursor
        j = auth_get("/markets", params=params)
        for m in j.get("markets", []):
            t = (m.get("ticker") or "")
            if "BTC15M" in t or "BTC" in t and "15M" in t:
                markets.append(m)
        cursor = j.get("cursor")
        if not cursor:
            break

    if not markets:
        # fallback: scan all and grep loosely
        print("  (no exact BTC15M match in first 300; scanning all open for BTC)")
        allm = []
        cursor = None
        for _ in range(3):
            params = {"limit": 100, "status": "open"}
            if cursor:
                params["cursor"] = cursor
            j = auth_get("/markets", params=params)
            allm.extend(j.get("markets", []))
            cursor = j.get("cursor")
            if not cursor:
                break
        markets = [m for m in allm if "BTC" in (m.get("ticker") or "")]

    if not markets:
        print("  NO BTC MARKETS OPEN AT ALL — venue has no BTC flow")
        return

    for m in markets[:8]:
        ticker = m.get("ticker")
        ya = float(m.get("yes_ask", 0) or 0)
        yb = float(m.get("yes_bid", 0) or 0)
        na = float(m.get("no_ask", 0) or 0)
        nb = float(m.get("no_bid", 0) or 0)
        vol = float(m.get("volume_24h") or 0)
        volc = float(m.get("volume", 0) or 0)
        two_sided = (yb > 0 and ya > 0) or (nb > 0 and na > 0)
        print(f"  {ticker}")
        print(f"    title: {m.get('title','')[:70]}")
        print(f"    Y[{yb:.2f}/{ya:.2f}] N[{nb:.2f}/{na:.2f}] vol24h={vol:.0f} vol={volc:.0f} two_sided={two_sided} close={m.get('close_time')}")

    # ---- 3. for the most liquid BTC market, get orderbook + recent trades ----
    best = max(markets, key=lambda m: float(m.get("volume_24h") or 0) + float(m.get("volume") or 0))
    ticker = best.get("ticker")
    print(f"\n=== ORDERBOOK + TRADES: {ticker} ===")
    try:
        ob = auth_get(f"/markets/{ticker}/orderbook")
        fp = ob.get("orderbook_fp", {})
        yd = fp.get("yes_dollars", [])[:5]
        nd = fp.get("no_dollars", [])[:5]
        print(f"  YES levels (top5): {yd}")
        print(f"  NO  levels (top5): {nd}")
    except Exception as e:
        print(f"  orderbook ERR: {e}")

    try:
        tr = auth_get(f"/markets/{ticker}/trades", params={"limit": 50})
        trades = tr.get("trades", tr.get("orderbook", []))
        if isinstance(trades, list) and trades:
            print(f"  recent trades: {len(trades)}")
            for t in trades[:8]:
                ts = t.get("created_time") or t.get("timestamp")
                p = t.get("price") or t.get("yes_price") or t.get("no_price")
                c = t.get("count") or t.get("contract_count")
                print(f"    t={ts} side={t.get('taker_side') or t.get('side')} px={p} cnt={c}")
        else:
            print(f"  no trades returned ({type(trades)})")
    except Exception as e:
        print(f"  trades ERR: {e}")


if __name__ == "__main__":
    main()
