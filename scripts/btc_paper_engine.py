#!/usr/bin/env python3
"""BTC short paper-test engine — simulates short trades against live BTC spot, logs P&L."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import httpx  # noqa: E402

PUBLIC = ROOT / "app" / "public"
TICKERS = ["KXBTC15M", "KXBTC1H", "KXBTC4H"]
PAPER_FILE = PUBLIC / "btc_paper_trades.json"
STATE_FILE = ROOT / "data" / "btc_paper_state.json"


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def get_spot() -> float | None:
    try:
        r = httpx.get("https://api.coinbase.com/v2/prices/BTC-USD/spot", timeout=10)
        return float(r.json()["data"]["amount"])
    except Exception:
        pass
    try:
        r = httpx.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=10)
        return float(r.json()["price"])
    except Exception:
        pass
    return None


def simulate_short(spot: float, entry_spot: float, notional_usd: float) -> float:
    """Short P&L in USD: profit when spot falls, loss when spot rises."""
    move = (entry_spot - spot) / entry_spot
    return move * notional_usd


def run_once():
    spot = get_spot()
    if spot is None:
        log("spot feed unavailable")
        return

    trades = load_json(PAPER_FILE, [])
    state = load_json(STATE_FILE, {"last_spot": spot, "trades": [], "session_pnl_cents": 0})
    state["last_spot"] = spot
    state["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Sync trades
    state["trades"] = trades

    # Update open positions
    pnl = 0.0
    for t in trades:
        if t.get("status") == "open":
            t["current_spot"] = spot
            t["pnl_usd"] = simulate_short(spot, t["entry_spot"], t.get("notional_usd", 0))
            pnl += t["pnl_usd"]
        elif t.get("status") == "closed":
            pnl += t.get("pnl_usd", 0)

    state["session_pnl_usd"] = pnl
    save_json(STATE_FILE, state)
    log(f"spot=${spot:,.2f} | open={sum(1 for t in trades if t.get('status')=='open')} | P&L=${pnl:+.2f}")


def main():
    log("BTC paper-test engine starting — short-only, no live capital")
    while True:
        try:
            run_once()
        except Exception as exc:
            log(f"warn: {repr(exc)[:80]}")
        time.sleep(10)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("stopped")
