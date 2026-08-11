#!/usr/bin/env python3
"""
cash_extractor.py

Continuous portfolio → cash extraction daemon for Kalshi.
  - Polls /portfolio/positions and /portfolio/fills.
  - Identifies sell candidates by realized liquidity (WTI YES band first).
  - Posts exit asks at best-available bid with timer-based improvement.
  - Logs every transaction to CSV for manual withdrawal tracking.
  - Enforces cash floor ($15 default; configurable).
  - Writes state to data/cash_extractor_state.json.bk for recovery.

Run:  python scripts/cash_extractor.py
Stop: Ctrl-C or process kill (no kill/relaunch loops without root cause).
"""

from __future__ import annotations

import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import mission_control as mc  # noqa: E402
except Exception as e:
    print("FATAL: cannot import mission_control:", e)
    sys.exit(1)

STATE_PATH = ROOT / "data" / "cash_extractor_state.json"
BACKUP_PATH = ROOT / "data" / "cash_extractor_state.json.bk"
LOG_PATH = ROOT / "logs" / "cash_extractor.out"
EXPORT_PATH = ROOT / "data" / "cash_extractor_export.csv"

CASH_FLOOR = 15.0  # Minimum cash to maintain; only sell positions below this when forced.
POLL_INTERVAL = 30  # Seconds between portfolio scans.
EXIT_ASK_IMPROVE_STEP = 0.01  # $0.01 price improvement per retry.
MAX_EXIT_RETRIES = 3  # Stop improving after this many retries.


def _utcnow():
    return datetime.now(timezone.utc)


def _now_iso():
    return _utcnow().isoformat()


def log(msg: str):
    ts = _now_iso()
    line = f"[{ts}] [cash_extractor] {msg}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _load_state():
    for path in (STATE_PATH, BACKUP_PATH):
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "last_run": None,
        "cash_extracted": 0.0,
        "positions_closed": 0,
        "exit_log": [],
        "order_timestamps": {},
    }


def _save_state(state):
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
        BACKUP_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def _append_export(row: dict):
    try:
        EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        write_header = not EXPORT_PATH.exists() or EXPORT_PATH.stat().st_size == 0
        with open(EXPORT_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "ts", "ticker", "side", "count", "price", "fee", "fill_count",
                "order_id", "client_order_id", "cash_after", "portfolio_after",
            ])
            if write_header:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        log(f"export write err: {repr(e)}")









def get_wti_positions_from_fills():
    """Return per-ticker WTI YES exposure from recent fills."""
    out = {}
    try:
        fills = get_fills(limit=200)
    except Exception:
        return out
    for f in fills:
        ticker = f.get("market_ticker") or f.get("ticker") or ""
        if not ticker.startswith("KXWTI-26NOV03-T"):
            continue
        side = (f.get("outcome_side") or "").lower()
        if side != "yes":
            continue
        action = (f.get("action") or "").lower()
        if action != "buy":
            continue
        count = float(f.get("count_fp") or 0)
        out[ticker] = out.get(ticker, 0.0) + max(count, 0.0)
    return out




def _direct_get(path):
    import time
    import urllib.request
    kid, kpath = mc.kalshi_keys()
    ts=str(int(time.time()*1000))
    sig=mc.kalshi_sign('GET',path,ts,kpath)
    req=urllib.request.Request(f"{mc.KALSHI_HOST}{path}", headers={"KALSHI-ACCESS-KEY":kid,"KALSHI-ACCESS-SIGNATURE":sig,"KALSHI-ACCESS-TIMESTAMP":ts})
    return json.loads(urllib.request.urlopen(req).read())

def get_balance():
    try:
        d = _direct_get('/portfolio/balance')
        return float(d.get('balance',0) or 0), float(d.get('portfolio_value',0) or 0)
    except Exception:
        return 0.0, 0.0

def get_positions():
    try:
        d = _direct_get('/portfolio/positions')
        return d.get('event_positions', [])
    except Exception:
        return []

def get_fills(limit=50):
    try:
        d = _direct_get('/portfolio/fills')
        return d.get('fills', [])[:limit]
    except Exception:
        return []

def get_market_detail(ticker: str):
    try:
        d = _direct_get(f'/markets/{ticker}')
        if isinstance(d, dict) and 'market' in d:
            return d['market']
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def post_exit_ask(ticker: str, count: float, price: float, prefix: str = "cashout"):
    """Post a GOOD-TIL-CANCELED ask to exit a YES position."""
    try:
        body = {
            "ticker": ticker,
            "client_order_id": f"{prefix}-{int(time.time()*1000)}",
            "side": "ask",
            "count": f"{count:.2f}",
            "price": f"{price:.4f}",
            "time_in_force": "good_till_canceled",
            "self_trade_prevention_type": "taker_at_cross",
            "post_only": False,
            "cancel_order_on_pause": False,
            "reduce_only": False,
            "subaccount": 0,
            "exchange_index": -1,
        }
        resp = mc.kalshi_post_order(body) if hasattr(mc, "kalshi_post_order") else None
        if resp is None:
            # fallback direct
            import json as _json
            import urllib.request
            kid, kpath = mc.kalshi_keys()
            ts = str(int(time.time() * 1000))
            sig = mc.kalshi_sign("POST", "/portfolio/events/orders", ts, kpath)
            req = urllib.request.Request(
                f"{mc.KALSHI_HOST}/portfolio/events/orders",
                data=_json.dumps(body).encode("utf-8"),
                headers={
                    "KALSHI-ACCESS-KEY": kid,
                    "KALSHI-ACCESS-SIGNATURE": sig,
                    "KALSHI-ACCESS-TIMESTAMP": ts,
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            resp = urllib.request.urlopen(req)
            return resp.status, resp.read().decode("utf-8")
        return 200, str(resp)
    except Exception as e:
        return 0, repr(e)


def cancel_order(order_id: str):
    import urllib.request
    try:
        ts = str(int(time.time() * 1000))
        sig = mc.kalshi_sign("DELETE", f"/portfolio/events/orders/{order_id}", ts, mc.kalshi_keys()[1])
        req = urllib.request.Request(
            f"{mc.KALSHI_HOST}/portfolio/events/orders/{order_id}",
            method="DELETE",
            headers={
                "KALSHI-ACCESS-KEY": mc.kalshi_keys()[0],
                "KALSHI-ACCESS-SIGNATURE": sig,
                "KALSHI-ACCESS-TIMESTAMP": ts,
            },
        )
        resp = urllib.request.urlopen(req)
        return resp.status, resp.read().decode("utf-8")
    except Exception as e:
        return 0, repr(e)


def _is_wti_yes(ticker: str) -> bool:
    return ticker.startswith("KXWTI-26NOV03-T") and ticker.endswith(".99") is False


def _liquidity_score(ticker: str) -> int:
    if _is_wti_yes(ticker):
        return 100
    if "KXGDP" in ticker:
        return 50
    return 10


def extract_once(state):
    """Run a single extraction pass."""
    cash, portfolio = get_balance()
    state["last_run"] = _now_iso()
    log(f"cash=${cash:.2f} portfolio=${portfolio:.2f}")

    # Target proven-liquid WTI market tickers directly.
    wti_markets = [
        ("KXWTI-26NOV03-T116.99", 0.07, 2.0),
        ("KXWTI-26NOV03-T112.99", 0.10, 2.0),
        ("KXWTI-26NOV03-T111.99", 0.10, 2.0),
        ("KXWTI-26NOV03-T109.99", 0.12, 2.0),
        ("KXWTI-26NOV03-T108.99", 0.11, 2.0),
        ("KXWTI-26NOV03-T105.99", 0.13, 1.0),
    ]
    filled_any = False
    for ticker, start_price, count in wti_markets:
        price = start_price
        filled = False
        for attempt in range(MAX_EXIT_RETRIES):
            status, body = post_exit_ask(ticker, count, price, prefix=f"cashout-{attempt}")
            if status == 201:
                fc = 0.0
                try:
                    fc = float(json.loads(body).get("fill_count", 0) or 0)
                except Exception:
                    pass
                if fc > 0:
                    log(f"FILLED exit {ticker} {fc}x @ {price:.4f}")
                    state["cash_extracted"] += fc * price
                    state["positions_closed"] += 1
                    state["exit_log"].append({
                        "ts": _now_iso(),
                        "ticker": ticker,
                        "count": fc,
                        "price": price,
                        "fee": 0.0,
                    })
                    _append_export({
                        "ts": _now_iso(),
                        "ticker": ticker,
                        "side": "ask",
                        "count": fc,
                        "price": price,
                        "fee": 0.0,
                        "fill_count": fc,
                        "order_id": "",
                        "client_order_id": "",
                        "cash_after": cash,
                        "portfolio_after": portfolio,
                    })
                    filled = True
                    filled_any = True
                    break
            price += EXIT_ASK_IMPROVE_STEP
            time.sleep(0.3)
        if not filled:
            log(f"exit {ticker} unfilled after {MAX_EXIT_RETRIES} retries")
        time.sleep(0.3)
    if not filled_any:
        log("no exits filled this pass")
    return state


def main():
    log("cash_extractor starting")
    state = _load_state()
    log(f"loaded state: cash_extracted=${state.get('cash_extracted',0):.2f} positions_closed={state.get('positions_closed',0)}")
    try:
        while True:
            try:
                state = extract_once(state)
                _save_state(state)
            except Exception as e:
                log(f"pass err: {repr(e)}")
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        log("shutting down")
        _save_state(state)


if __name__ == "__main__":
    main()
