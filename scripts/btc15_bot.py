# file_id: SOM-PY-0925-v1.0.0 name: btc15_bot.py description: BTC 15-min momentum bot — spot-momentum signal vs Kalshi KXBTC15M lag, micro-size live fires through mission control, hard caps + session stop, UUID ledger tracking project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [btc, momentum, kalshi, trading, live, uuid] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""btc15_bot.py — trade KXBTC15M ("BTC up in next 15 min?") on spot momentum.

Thesis (corpus-backed): Kalshi 15-min BTC binaries lag spot by seconds-minutes;
co-move follow-through is the documented edge. When spot moves sharply and the
binary hasn't repriced, take the cheap side (taker, 1 contract).

Gates (non-negotiable): 1 contract/fire, <= MAX_OPEN positions, no entries in the
final NO_TRADE_LAST_S of a market, session stop at SESSION_STOP_CENTS, MC kill
switch honored on every fire (server-side).

Fires go through mission control /api/order so mint (0x3A4/0x3A5), ack (0x3A6),
ledger rows, and risk gates stay centralized. Settles are written back here.

Run:  .venv311/Scripts/python scripts/btc15_bot.py [--paper]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import httpx  # noqa: E402
import sb  # noqa: E402
import uuid_ledger as L  # noqa: E402

MC = os.getenv("MC_URL", "http://127.0.0.1:8420")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = "KXBTC15M"

# ---- tunables ----
POLL_S = 3                 # loop cadence
MOM_WINDOW_S = 180         # momentum lookback
MOM_THRESHOLD = 0.0004     # 4 bps over the window = signal
ENTRY_MAX_PRICE = 55       # don't chase: only enter when side cost <= 55c
CONTRACTS = 1
MAX_OPEN = 3
NO_TRADE_LAST_S = 120      # no entries in final 2 minutes
SESSION_STOP_CENTS = -300  # stop trading for the session at -$3
FEE_EST_CENTS = 2          # taker fee estimate per 50c contract

PASSKEY = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()
spot_hist: deque = deque(maxlen=600)   # (ts, price) ~30 min at 3s
traded_tickers: set = set()
session_pnl_cents = 0
open_positions: dict = {}  # ticker -> {side, entry, uuid}


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def spot_price(cx: httpx.Client) -> float | None:
    for url, path in (
        ("https://api.coinbase.com/v2/prices/BTC-USD/spot", ("data", "amount")),
        ("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", ("price",)),
    ):
        try:
            d = cx.get(url, timeout=8).json()
            for k in path:
                d = d[k]
            return float(d)
        except Exception:
            continue
    return None


def momentum(now_ts: float) -> float | None:
    if len(spot_hist) < 10:
        return None
    ref = None
    for ts, px in spot_hist:
        if ts <= now_ts - MOM_WINDOW_S:
            ref = px
        else:
            break
    if not ref:
        return None
    return (spot_hist[-1][1] - ref) / ref


def current_market(cx: httpx.Client) -> dict | None:
    from datetime import datetime, timezone
    r = cx.get(f"{KALSHI}/markets", params={"limit": 5, "status": "open", "series_ticker": SERIES}, timeout=10)
    best = None
    now = time.time()
    for m in r.json().get("markets", []):
        try:
            close = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
            ya = float(m.get("yes_ask_dollars") or 0)
            yb = float(m.get("yes_bid_dollars") or 0)
        except Exception:
            continue
        ttl = close - now
        if ttl < NO_TRADE_LAST_S:
            continue
        if not (0 < ya < 1):
            continue
        row = {"ticker": m["ticker"], "yes_ask": round(ya * 100), "yes_bid": round(yb * 100),
               "ttl": ttl, "close": m["close_time"]}
        if best is None or row["ttl"] < best["ttl"]:
            best = row
    return best


def fire(ticker: str, side: str, price_cents: int) -> dict:
    r = httpx.post(f"{MC}/api/order", json={
        "ticker": ticker, "side": side, "price": price_cents, "count": CONTRACTS,
        "mode": "live", "passkey": PASSKEY, "confirm": "FIRE"}, timeout=30)
    return {"http": r.status_code, **r.json()}


def settle_closed(cx: httpx.Client):
    """Resolve traded markets that closed; write settlement + realized P&L to the ledger."""
    global session_pnl_cents
    for ticker in list(traded_tickers):
        try:
            r = cx.get(f"{KALSHI}/markets/{ticker}", timeout=10)
            m = r.json().get("market", {})
        except Exception:
            continue
        result = (m.get("result") or "").lower()
        if result not in ("yes", "no"):
            continue
        pos = open_positions.get(ticker)
        if not pos:
            traded_tickers.discard(ticker)
            continue
        con = sb.sb_conn()
        cur = con.cursor()
        settle_cents = 100 if result == "yes" else 0
        mkt_uuid = L.mint_market_uuid(ticker)
        L.settle(cur, ticker, mkt_uuid, settle_cents)
        con.commit()
        cur.execute("SELECT realized_pnl_cents FROM uuid_positions WHERE ticker=%s AND side=%s",
                    (ticker, pos["side"]))
        pnl = cur.fetchone()[0]
        con.close()
        session_pnl_cents += pnl
        won = (result == pos["side"])
        log(f"SETTLED {ticker}: result={result} our_side={pos['side']} -> {'WIN' if won else 'LOSS'} "
            f"realized={pnl}c session={session_pnl_cents}c")
        open_positions.pop(ticker, None)
        traded_tickers.discard(ticker)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", action="store_true", help="force paper mode (no live fires)")
    args = ap.parse_args()
    if args.paper:
        log("PAPER mode requested — but fire path is live-gated; use MC ticket for paper. Exiting.")
        return 2

    log(f"btc15_bot start | momentum {MOM_THRESHOLD*1e4:.0f}bps/{MOM_WINDOW_S}s | entry<= {ENTRY_MAX_PRICE}c | "
        f"{CONTRACTS}ct | max_open={MAX_OPEN} | stop={SESSION_STOP_CENTS}c")
    # sanity: MC up + keys armed
    s = httpx.get(f"{MC}/api/stats", timeout=10).json()
    assert s.get("keys"), "MC reports no Kalshi keys"
    log(f"MC ok | kill={s['kill']} corpus={'online' if s['corpus']['online'] else 'DOWN'}")

    with httpx.Client(headers={"Accept-Encoding": "identity"}) as cx:
        while True:
            if session_pnl_cents <= SESSION_STOP_CENTS:
                log(f"SESSION STOP hit ({session_pnl_cents}c). Halting.")
                return 1
            px = spot_price(cx)
            if px:
                spot_hist.append((time.time(), px))
            mom = momentum(time.time())
            try:
                settle_closed(cx)
            except Exception as e:
                log(f"settle warn: {repr(e)[:100]}")
            if mom is None:
                time.sleep(POLL_S)
                continue
            if len(open_positions) >= MAX_OPEN:
                time.sleep(POLL_S)
                continue
            mkt = current_market(cx)
            if not mkt or mkt["ticker"] in traded_tickers:
                time.sleep(POLL_S)
                continue

            # signal -> side + entry price (taker at the ask)
            if mom >= MOM_THRESHOLD and mkt["yes_ask"] <= ENTRY_MAX_PRICE:
                side, price = "yes", mkt["yes_ask"]
            elif mom <= -MOM_THRESHOLD:
                no_ask = 100 - mkt["yes_bid"]
                if no_ask > ENTRY_MAX_PRICE:
                    time.sleep(POLL_S)
                    continue
                side, price = "no", no_ask
            else:
                time.sleep(POLL_S)
                continue

            log(f"SIGNAL mom={mom*1e4:+.1f}bps -> {side.upper()} {price}c {mkt['ticker']} (ttl {mkt['ttl']:.0f}s)")
            try:
                resp = fire(mkt["ticker"], side, price)
            except Exception as e:
                log(f"fire exception: {repr(e)[:120]}")
                time.sleep(POLL_S)
                continue
            if resp.get("ok"):
                traded_tickers.add(mkt["ticker"])
                open_positions[mkt["ticker"]] = {"side": side, "entry": price, "uuid": resp.get("uuid")}
                ack = resp.get("ack") or {}
                log(f"FILLED {side} x{CONTRACTS} @ {ack.get('average_fill_price', price)} "
                    f"fee={ack.get('average_fee_paid')} uuid={str(resp.get('uuid'))[:13]}… coi={resp.get('client_order_id')}")
            else:
                log(f"FIRE REJECTED: HTTP {resp.get('http')} {json.dumps(resp)[:200]}")
                traded_tickers.add(mkt["ticker"])  # don't hammer a rejecting market
            time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
