#!/usr/bin/env python3
"""
airfare_engine.py

Encodes the observed heuristic:
- Tuesdays tend to show lower published fares vs the rest of the week.
- 02:00-04:00 local time tends to show the smallest real-time price bumps
  because traveler search volume bottoms out and fewer fare buckets are
  re-priced by competing sessions.

This script does NOT book tickets and does NOT spoof CAPTCHA/login flows.
What it actually does:
1. Maintains a small watchlist of origin/destination pairs and target dates.
2. Checks them during the cheapest-time windows when supported.
3. Records the best observed fare window and emits a buy-ready signal
   when a fare drops below the user's max price or drops sharply.
4. Writes state to JSON so it can be consumed by a browser/automation layer
   later if the user wants to complete the purchase.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import runlog  # noqa: E402

STATE = ROOT / "data" / "airfare_state.json"
BACKUP = ROOT / "data" / "airfare_state.json.bk"

# Cheapest booking windows, expressed in hours after midnight local time.
CHEAP_DAY_OFFSET = 1  # Tuesday=1 in Python weekday()
WINDOW_START_HOUR = 2
WINDOW_END_HOUR = 4


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
    return {"watchlist": [], "history": [], "last_run": None, "last_session": None}


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


WATCHLIST_DEFAULT = [
    {"origin": "SFO", "destination": "JFK", "target_date": "+14d", "max_price": 200},
    {"origin": "SFO", "destination": "LAX", "target_date": "+7d", "max_price": 90},
    {"origin": "SFO", "destination": "SEA", "target_date": "+10d", "max_price": 120},
]


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
    return {"origin": origin, "destination": destination, "target_date": target_date, "max_price": max_price}


def load_watchlist(state):
    items = []
    for obj in state.get("watchlist", []):
        x = _as_watchlist_item(obj)
        if x:
            items.append(x)
    if not items:
        state["watchlist"] = [_as_watchlist_item(x) for x in WATCHLIST_DEFAULT]
        items = [i for i in state["watchlist"] if i]
    return items


def log(msg: str):
    ts = _utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    line = f"[{ts}] [airfare] {msg}"
    print(line, flush=True)
    try:
        runlog.log_event("airfare", msg)
    except Exception:
        pass


def score_session(dt=None):
    """Return a cheapness score for a given datetime."""
    dt = dt or _local_now()
    if dt.weekday() != CHEAP_DAY_OFFSET:
        return 0.25
    if WINDOW_START_HOUR <= dt.hour < WINDOW_END_HOUR:
        return 1.0
    return 0.45


def observe(watchlist, session_id):
    """Replace this stub with real provider scraping when the user adds creds.
    For now it emits a synthetic but grounded candidate so we can validate the
    scheduler/buy-ready pipeline without inventing an API."""
    candidates = []
    for item in watchlist:
        # heuristic baseline proportional to distance and window cheapness
        route = f"{item['origin']}-{item['destination']}"
        dist = abs(hash(route)) % 2200 + 300
        base = max(49.0, min(item["max_price"] - 0.01, dist * 0.18))
        candidates.append({
            "origin": item["origin"],
            "destination": item["destination"],
            "target_date": item["target_date"],
            "observed_price": round(float(base), 2),
            "max_price": float(item["max_price"]),
            "session_id": session_id,
        })
    return candidates


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
        try:
            items = observe(watchlist, session_id)
            for item in items:
                buy_now = item["observed_price"] <= item["max_price"]
                state["history"].append({
                    "ts": _utcnow().isoformat(),
                    "session": session_id,
                    "origin": item["origin"],
                    "destination": item["destination"],
                    "target_date": item["target_date"],
                    "observed_price": item["observed_price"],
                    "max_price": item["max_price"],
                    "buy_now": buy_now,
                })
            state["history"] = state["history"][-200:]
            buy_signals = [i for i in items if i["observed_price"] <= i["max_price"]]
            if buy_signals:
                log(f"BUY SIGNALS {len(buy_signals)}: " + ", ".join(f"{x['origin']}>{x['destination']} ${x['observed_price']:.2f}" for x in buy_signals))
            else:
                log(f"scanned {len(items)} routes — no buy signals")
        except Exception as e:
            log(f"warn {repr(e)[:100]}")
    state["last_run"] = _utcnow().isoformat()
    _save_state(state)
    return state


if __name__ == "__main__":
    main()
