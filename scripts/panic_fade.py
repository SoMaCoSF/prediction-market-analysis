#!/usr/bin/env python3
"""
Panic fade detector — buys when price drops >10¢ in one poll cycle
and the YES bid is still >20¢ (room to fade back up).

Strategy from TurbineFi backtests:
- panic_fade: 93/96 profitable on KXBTC15M
- Mean reversion: 0/432 profitable (dead)
- Works by buying after violent drops, expecting mean reversion within window

Parameters:
- DROP_THRESHOLD: 10¢ drop in one cycle = panic
- MIN_BID: 20¢ minimum YES bid after drop = still valuable
- MAX_POSITIONS: 2 concurrent fade positions
- COOLDOWN: 120s between fades
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from mission_control import KALSHI_HOST, kalshi_keys, kalshi_sign  # noqa: E402

LOG = ROOT / "logs" / "panic_fade.out"
STATE = ROOT / "data" / "panic_fade_state.json"
DROP_THRESHOLD = 0.10  # 10¢ drop
MIN_BID = 0.20  # 20¢ minimum after drop
MAX_POSITIONS = 2
COOLDOWN_SEC = 120
POLL_INTERVAL = 5  # faster cycle


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
    return {"last_prices": {}, "last_signal_ts": {}, "positions": 0}


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

        last_price = float(m.get("last_price_dollars", 0) or 0)
        yes_bid = float(m.get("yes_bid_dollars", 0) or 0)
        yes_ask = float(m.get("yes_ask_dollars", 0) or 0)
        vol = float(m.get("volume_24h", 0) or 0)

        if last_price <= 0 or yes_bid <= 0:
            continue

        prev_price = state["last_prices"].get(ticker, last_price)
        price_drop = prev_price - last_price

        # Panic fade: price dropped >10¢ in one cycle, bid still >20¢
        if price_drop >= DROP_THRESHOLD and yes_bid >= MIN_BID:
            last_sig = state["last_signal_ts"].get(ticker, 0)
            if now - last_sig > COOLDOWN_SEC and state["positions"] < MAX_POSITIONS:
                signals.append({
                    "type": "PANIC_FADE",
                    "ticker": ticker,
                    "drop_cents": round(price_drop * 100, 2),
                    "yes_bid_cents": round(yes_bid * 100, 2),
                    "yes_ask_cents": round(yes_ask * 100, 2),
                    "volume": vol,
                })
                state["last_signal_ts"][ticker] = now
                state["positions"] += 1

        state["last_prices"][ticker] = last_price

    for sig in signals:
        log(f"FADE {sig['type']}: {sig['ticker'][:60]} | drop={sig['drop_cents']}¢ | bid={sig['yes_bid_cents']}¢ | vol={sig['volume']}")

    if not signals:
        log(f"Scanned {len(markets)} markets — no panic fades")

    save_state(state)


def main():
    log("PANIC FADE STARTED")
    log(f"Params: drop>{DROP_THRESHOLD*100}¢, bid>={MIN_BID*100}¢, max={MAX_POSITIONS} positions, cooldown={COOLDOWN_SEC}s")
    state = load_state()
    while True:
        try:
            run_once(state)
        except Exception as e:
            log(f"ERROR: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
