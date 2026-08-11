# file_id: SOM-PY-0972-v1.0.0 name: whale_copier.py description: Whale copier — aggregate Polymarket trades per wallet, rank top whales by flow, copy their fresh prints to mapped Kalshi crypto windows with size scaled to conviction; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [whale, copier, polymarket, follow, live] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""whale_copier.py — copy the smart money, wallet-aware.

1. Poll top Polymarket markets' public trades (keyless data-api).
2. Aggregate by proxyWallet over the rolling window; top wallets by USD flow
   = the whale leaderboard (size+recurrence = informed flow proxy).
3. When a top wallet prints a NEW large trade on a crypto-mappable market
   (BTC/ETH/SOL keywords) -> copy on the matching Kalshi 15M window,
   direction = whale side, size scaled by print size (1-3ct).
Caps: $5/day, 3 concurrent, one copy per print (seed dedupe). Trades via MC.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import httpx  # noqa: E402
import os as _os  # noqa: E402
FLEET_HALTED = _os.getenv("FLEET_HALTED", "0") == "1"
import runlog  # noqa: E402
import sb  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
MC = os.getenv("MC_URL", "http://127.0.0.1:8420")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
PK = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()

POLL_S = 60
TOP_MARKETS = 15
MIN_PRINT_USD = 5000.0
TOP_WHALES = 5
DAILY_CAP = 1500          # cents
MAX_CONC = 3
CRYPTO_MAP = {"bitcoin": "KXBTC15M", "btc": "KXBTC15M", "ethereum": "KXETH15M", "eth": "KXETH15M",
              "solana": "KXSOL15M", "sol": "KXSOL15M"}

wallet_flow: dict[str, float] = defaultdict(float)
seen_prints: set[str] = set()
copies: list[dict] = []
spent_today = 0.0
today = time.strftime("%Y-%m-%d")


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] [copier] {m}", flush=True)
    runlog.log_event("copier", m)


def fire(ticker, side, price, count=1):
    try:
        r = httpx.post(f"{MC}/api/order", json={"ticker": ticker, "side": side, "price": price,
                       "count": count, "mode": "live", "passkey": PK, "confirm": "FIRE"}, timeout=30)
        d = r.json()
        return {"ok": bool(d.get("ok")), "filled": float((d.get("ack") or {}).get("fill_count") or 0)}
    except Exception:
        return {"ok": False, "filled": 0.0}


def publish_board():
    """The wallet leaderboard — top whales by flow, for the poly panel."""
    try:
        import json as _json
        top = sorted(wallet_flow.items(), key=lambda kv: -kv[1])[:10]
        board = [{"wallet": w[:12] + "…", "flow_usd": round(v), "rank": i + 1}
                 for i, (w, v) in enumerate(top)]
        con = sb.sb_conn()
        con.autocommit = True
        con.cursor().execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('copier:board', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (_json.dumps(board),))
        con.close()
    except Exception:
        pass


def map_series(text):
    low = text.lower()
    for k, v in CRYPTO_MAP.items():
        if k in low:
            return v
    return None


def copy_print(cx, whale, side, usd, series):
    global spent_today
    if FLEET_HALTED:
        return
    if len(copies) >= MAX_CONC or spent_today >= DAILY_CAP / 100:
        return
    try:
        r = cx.get(f"{KALSHI}/markets", params={"limit": 3, "status": "open", "series_ticker": series}, timeout=15)
        for m in r.json().get("markets", []):
            ya = round(float(m.get("yes_ask_dollars") or 0) * 100)
            yb = round(float(m.get("yes_bid_dollars") or 0) * 100)
            if not (0 < ya < 100):
                continue
            kside, price = ("yes", ya) if side == "BUY" else ("no", 100 - yb)
            if not (1 <= price <= 60):
                return
            qty = 1 if usd < 25000 else (2 if usd < 75000 else 3)
            r2 = fire(m["ticker"], kside, price, qty)
            if r2["ok"] and r2["filled"] > 0:
                copies.append({"ticker": m["ticker"], "side": kside, "price": price, "qty": qty})
                spent_today += price * qty / 100
                log(f"COPY {whale[:10]}… ${usd:,.0f} {side} -> {kside.upper()} x{qty} @{price}c {series}")
                return
            # illiquid fill: try next market instead of giving up
            continue
    except Exception as e:
        log(f"copy warn {repr(e)[:50]}")
    log(f"COPY {whale[:10]}… ${usd:,.0f} {side} -> no live Kalshi market for {series}")


def main():
    global spent_today, today
    fleetlib.acquire_lock("copier")
    log(f"start | print>=${MIN_PRINT_USD:,.0f} top {TOP_WHALES} wallets cap ${DAILY_CAP/100:.2f}/day")
    with httpx.Client(headers={"Accept-Encoding": "identity"}, timeout=25) as cx:
        while True:
            fleetlib.checkin("copier")
            try:
                if time.strftime("%Y-%m-%d") != today:
                    today = time.strftime("%Y-%m-%d")
                    spent_today = 0.0
                    wallet_flow.clear()
                mkts = cx.get("https://gamma-api.polymarket.com/markets",
                              params={"limit": TOP_MARKETS, "active": "true", "order": "volume24hr", "ascending": "false"},
                              timeout=20).json()
                for m in mkts:
                    cid = m.get("conditionId") or m.get("condition_id")
                    q = (m.get("question") or "")
                    if not cid:
                        continue
                    try:
                        trades = cx.get("https://data-api.polymarket.com/trades",
                                        params={"market": cid, "limit": 50}, timeout=20).json()
                    except Exception:
                        continue
                    for t in trades:
                        try:
                            size = float(t.get("size") or 0)
                            price = float(t.get("price") or 0)
                        except Exception:
                            continue
                        usd = size * price
                        wallet = t.get("proxyWallet") or t.get("maker_address") or ""
                        if wallet:
                            wallet_flow[wallet] += usd
                        pid = str(t.get("transaction_hash") or t.get("id") or "")
                        if usd >= MIN_PRINT_USD and pid and pid not in seen_prints:
                            seen_prints.add(pid)
                            top = sorted(wallet_flow, key=lambda w: -wallet_flow[w])[:TOP_WHALES]
                            if wallet in top:
                                series = map_series(q)
                                if series:
                                    copy_print(cx, wallet, (t.get("side") or "").upper(), usd, series)
                                else:
                                    log(f"whale ${usd:,.0f} {(t.get('side') or '').upper()} | no kalshi map: {q[:44]}")
                if len(seen_prints) > 5000:
                    seen_prints.clear()
                publish_board()
                # publish the whale leaderboard (flow-ranked)
                try:
                    import json as _json
                    board = [{"wallet": w[:12], "flow_usd": round(wallet_flow[w])}
                             for w in sorted(wallet_flow, key=lambda w: -wallet_flow[w])[:10]]
                    con = sb.sb_conn()
                    con.autocommit = True
                    con.cursor().execute(
                        "INSERT INTO mc_state (k, v, updated_at) VALUES ('copier:board', %s, now()) "
                        "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
                        (_json.dumps(board),))
                    con.close()
                except Exception:
                    pass
            except Exception as e:
                log(f"cycle warn {repr(e)[:60]}")
            time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
