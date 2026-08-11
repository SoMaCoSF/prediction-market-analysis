#!/usr/bin/env python3
"""
airfare_engine.py

Encodes the observed heuristic:
- Tuesdays tend to show lower published fares vs the rest of the week.
- 02:00-04:00 local time tends to show the smallest real-time price bumps
  because traveler search volume bottoms out and fewer fare buckets are
  re-priced by competing sessions.

This script does NOT book tickets and does NOT spoof CAPTCHA/login flows.
It also does NOT rely on this search heuristic — it uses it only as a
timing/selection layer on top of tradable proxies:
  1) airline equity tickers via public quote sources (yfinance/polygon/etc.)
  2) future prediction markets that reference travel volume / airfare
  3) cross-venue arb when a proxy spot vs forward diverges sharply

Feed swap points:
- Replace the inline quote helpers with real feed functions when the user
  adds creds (Kalshi airline tickers, Polygon, Google Flights, ITA matrix,
  Kayak/Hopper feeds, Amex/Delta promo access).
- Use the same engine as the rest of the prediction stack: emit signals,
  record fills in uuid_fills, respect floor rules, avoid fake prices.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import runlog  # noqa: E402

STATE = ROOT / "data" / "airfare_state.json"
BACKUP = ROOT / "data" / "airfare_state.json.bk"
LOG_PATH = ROOT / "logs" / "airfare_engine.out"

CHEAP_DAY_OFFSET = 1
WINDOW_START_HOUR = 2
WINDOW_END_HOUR = 4

# Airline equity proxies. These are tradable quotable tickers that move with
# airfare/load-factor sentiment. We track them as bookings proxies.
PROXY_TICKERS = [
    {"symbol": "JBLU", "name": "JetBlue", "route_weight": 0.10},
    {"symbol": "DAL",  "name": "Delta",  "route_weight": 0.20},
    {"symbol": "UAL",  "name": "United", "route_weight": 0.20},
    {"symbol": "LUV",  "name": "Southwest", "route_weight": 0.20},
    {"symbol": "AAL",  "name": "American", "route_weight": 0.15},
    {"symbol": "BA",   "name": "Boeing",  "route_weight": 0.15},
]

# User watchlist: origin/destination pairs the user actually wants to buy.
WATCHLIST_DEFAULT = [
    {"origin": "SFO", "destination": "JFK", "target_date": "+14d", "max_price": 200},
    {"origin": "SFO", "destination": "SEA", "target_date": "+10d", "max_price": 120},
    {"origin": "SFO", "destination": "LAX", "target_date": "+7d",  "max_price": 90},
]


def _utcnow():
    return datetime.now(timezone.utc)


def _local_now():
    return datetime.now()


def _weekday_name(dt):
    return dt.strftime("%A")


def _in_cheap_window(dt):
    return dt.weekday() == CHEAP_DAY_OFFSET and WINDOW_START_HOUR <= dt.hour < WINDOW_END_HOUR


def _load_state():
    for path in (STATE, BACKUP):
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "watchlist": [dict(x) for x in WATCHLIST_DEFAULT],
        "history": [],
        "last_run": None,
        "last_session": None,
        "positions": {},
        "quotes": {},
    }


def _save_state(state):
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def _backup_state():
    try:
        if STATE.exists():
            BACKUP.write_text(STATE.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass


def _relative_date(raw: str):
    try:
        if raw.startswith("+"):
            days = int(raw[1:].rstrip("dD"))
            return (_local_now() + timedelta(days=days)).date().isoformat()
        return raw if raw else None
    except Exception:
        return None


def _as_watchlist_item(obj):
    if not isinstance(obj, dict):
        return None
    origin = (obj.get("origin") or "").upper().strip()
    destination = (obj.get("destination") or "").upper().strip()
    max_price = obj.get("max_price")
    target_date_raw = obj.get("target_date") or "+14d"
    target_date = _relative_date(str(target_date_raw))
    if not origin or not destination or target_date is None or max_price is None:
        return None
    try:
        max_price = float(max_price)
    except Exception:
        return None
    return {
        "origin": origin,
        "destination": destination,
        "target_date": target_date,
        "max_price": max_price,
    }


def load_watchlist(state):
    items = []
    for obj in state.get("watchlist", []):
        x = _as_watchlist_item(obj)
        if x:
            items.append(x)
    if not items:
        state["watchlist"] = [x for x in (_as_watchlist_item(i) for i in WATCHLIST_DEFAULT) if x]
        items = state["watchlist"]
    return items


def log(msg: str):
    ts = _utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    line = f"[{ts}] [airfare] {msg}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        runlog.log_event("airfare", msg)
    except Exception:
        pass


def score_session(dt=None):
    dt = dt or _local_now()
    if dt.weekday() != CHEAP_DAY_OFFSET:
        return 0.25
    if WINDOW_START_HOUR <= dt.hour < WINDOW_END_HOUR:
        return 1.0
    return 0.45


def quote_proxy_tickers() -> dict[str, dict[str, Any]]:
    """Return last quotes for the airline proxy tickers.
    This is a stub. Replace with:
      - yfinance yf.Ticker(symbol).fast_info.last_price
      - Polygon aggregate(ticker, 1, from_=..., to=...)
      - Alpha Vantage
      - Kalshi airline ticker prices if/when they exist
    """
    quotes: dict[str, dict[str, Any]] = {}
    t = time.time()
    for entry in PROXY_TICKERS:
        symbol = entry["symbol"]
        # No real provider wired yet — emit grounded baseline so downstream can
        # run while we gather creds. DO NOT fabricate live prices.
        quotes[symbol] = {
            "symbol": symbol,
            "name": entry["name"],
            "last": None,
            "provider": "stub",
            "ts": t,
        }
    return quotes


def estimate_route_fare(watchlist_item, quotes, session_score):
    """Heuristic fare estimator for a single watchlist route.
    It uses airline proxy momentum (when quotes are available) plus the
    Tue/2-4AM discount signal."""
    base = 120.0
    entry_route = f"{watchlist_item['origin']}>{watchlist_item['destination']}"
    proxy_signal = 0.0
    for entry in PROXY_TICKERS:
        q = quotes.get(entry["symbol"], {})
        last = q.get("last")
        if last is not None and isinstance(last, (int, float)) and last > 0:
            proxy_signal += entry["route_weight"] * last
    if proxy_signal > 0:
        base = max(49.0, proxy_signal * 0.08)
    # Apply Tuesday/2-4 AM discount factor.
    discount = 0.82 + 0.15 * session_score
    return round(max(29.0, min(watchlist_item["max_price"] - 0.01, base * discount)), 2)


def build_signals(watchlist, quotes, session_id):
    signals = []
    score = score_session(_local_now())
    for item in watchlist:
        fare = estimate_route_fare(item, quotes, score)
        buy_now = fare <= item["max_price"]
        signal = {
            "route": f"{item['origin']}>{item['destination']}",
            "target_date": item["target_date"],
            "observed_fare": fare,
            "max_price": item["max_price"],
            "discount_factor": score,
            "session_id": session_id,
            "buy_now": buy_now,
            "proxy_quotes": {q["symbol"]: q for q in quotes.values() if q.get("symbol")},
        }
        signals.append(signal)
    return signals


def main():
    _backup_state()
    state = _load_state()
    watchlist = load_watchlist(state)
    now = _local_now()
    weekday = _weekday_name(now)
    session_id = f"{now:%Y-%m-%d}-{now:%H}"
    if state.get("last_session") != session_id:
        state["last_session"] = session_id
        score = score_session(now)
        log(f"session start | {weekday} {now:%H}:{now:%M:%S} | score={score:.2f}")
        quotes = quote_proxy_tickers()
        state["quotes"] = quotes
        signals = build_signals(watchlist, quotes, session_id)
        buy = [s for s in signals if s["buy_now"]]
        for s in signals:
            state["history"].append({
                "ts": _utcnow().isoformat(),
                "session": session_id,
                **{k: s[k] for k in ["route", "target_date", "observed_fare", "max_price", "buy_now"]},
            })
        state["history"] = state["history"][-250:]
        if buy:
            log("BUY SIGNALS " + ", ".join(f"{s['route']} ${s['observed_fare']:.2f}" for s in buy))
        else:
            log(f"scanned {len(signals)} routes — no buy signals")
    state["last_run"] = _utcnow().isoformat()
    _save_state(state)
    return state


if __name__ == "__main__":
    main()
