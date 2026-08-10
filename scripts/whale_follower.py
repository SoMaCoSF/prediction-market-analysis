#!/usr/bin/env python3
"""
Whale follower daemon — polls Kalshi markets for whale-sized volume spikes
and price moves, logs signals, and can trigger copy entries.

Strategy:
- Track volume_24h changes across all 200 markets
- Alert when volume spikes > $1k in a single poll cycle
- Track price moves > 5¢ in a single poll cycle
- Deduplicate signals per ticker within 60s cooldown
- Log to logs/whale_follower.out
"""
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from mission_control import KALSHI_HOST, kalshi_keys, kalshi_sign  # noqa: E402

LOG = ROOT / "logs" / "whale_follower.out"
STATE = ROOT / "data" / "whale_state.json"
WHALE_VOLUME_THRESHOLD = 1000  # $1k volume spike = whale
PRICE_MOVE_THRESHOLD = 0.05  # 5¢ price move
COOLDOWN_SEC = 60
POLL_INTERVAL = 10


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state():
    try:
        if STATE.exists():
            return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"last_volumes": {}, "last_prices": {}, "last_signal_ts": {}}


def save_state(state):
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def signed_get(path: str) -> dict:
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("GET", path, ts, kpath)
    headers = {
        "KALSHI-ACCESS-KEY": kid,
        "KALSHI-ACCESS-SIGNATURE": sig,
        "KALSHI-ACCESS-TIMESTAMP": ts,
    }
    r = httpx.get(f"{KALSHI_HOST}{path}", headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()


def ticker_key(ticker: str) -> str:
    return hashlib.md5(ticker.encode()).hexdigest()[:12]


def run_once(state: dict):
    now = time.time()
    try:
        data = signed_get("/markets?limit=200&status=open")
        markets = data.get("markets", [])
    except Exception as e:
        log(f"ERROR fetching markets: {e}")
        return

    signals = []
    for m in markets:
        ticker = m.get("ticker")
        if not ticker:
            continue

        vol = float(m.get("volume_24h", 0) or 0)
        last_price = float(m.get("last_price_dollars", 0) or 0)
        yes_bid = float(m.get("yes_bid_dollars", 0) or 0)
        yes_ask = float(m.get("yes_ask_dollars", 0) or 0)

        tk = ticker_key(ticker)
        prev_vol = state["last_volumes"].get(tk, 0)
        prev_price = state["last_prices"].get(tk, last_price)

        # Volume whale detection
        vol_delta = vol - prev_vol
        if vol_delta >= WHALE_VOLUME_THRESHOLD:
            last_sig = state["last_signal_ts"].get(tk, 0)
            if now - last_sig > COOLDOWN_SEC:
                signals.append({
                    "type": "VOLUME_WHALE",
                    "ticker": ticker,
                    "volume_delta": round(vol_delta, 2),
                    "yes_bid_cents": round(yes_bid * 100, 2),
                    "yes_ask_cents": round(yes_ask * 100, 2),
                    "last_price_cents": round(last_price * 100, 2),
                })
                state["last_signal_ts"][tk] = now

        # Price move detection
        if prev_price > 0 and abs(last_price - prev_price) >= PRICE_MOVE_THRESHOLD:
            last_sig = state["last_signal_ts"].get(tk, 0)
            if now - last_sig > COOLDOWN_SEC:
                signals.append({
                    "type": "PRICE_MOVE",
                    "ticker": ticker,
                    "price_delta_cents": round((last_price - prev_price) * 100, 2),
                    "yes_bid_cents": round(yes_bid * 100, 2),
                    "yes_ask_cents": round(yes_ask * 100, 2),
                    "last_price_cents": round(last_price * 100, 2),
                })
                state["last_signal_ts"][tk] = now

        state["last_volumes"][tk] = vol
        state["last_prices"][tk] = last_price

    for sig in signals:
        log(f"WHALE {sig['type']}: {sig['ticker'][:60]} | vol_delta=${sig.get('volume_delta', 0)} | price_delta={sig.get('price_delta_cents', 0)}¢ | bid={sig['yes_bid_cents']}¢ ask={sig['yes_ask_cents']}¢")

    if not signals:
        log(f"Scanned {len(markets)} markets — no whale signals")

    save_state(state)


def main():
    log("WHALE FOLLOWER STARTED")
    log(f"Threshold: volume>${WHALE_VOLUME_THRESHOLD}, price_move>{PRICE_MOVE_THRESHOLD*100}¢, cooldown={COOLDOWN_SEC}s")
    state = load_state()
    while True:
        try:
            run_once(state)
        except Exception as e:
            log(f"ERROR: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
