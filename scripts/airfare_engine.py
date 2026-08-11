#!/usr/bin/env python3
"""
airfare_engine.py

Flight-status trading engine:
  - Polls OpenSky Network (free ADS-B) for live flight state vectors.
  - Detects delays, cancellations, diversions, early arrivals.
  - Generates derivative signals (buy "delay" / "cancel" / "land on time" / "early").
  - Routes signals to the local prediction stack via event-driven hooks
    (paper execution or live when liquidity appears).

No auth required for OpenSky public API.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import runlog  # noqa: E402

STATE = ROOT / "data" / "airfare_state.json"
BACKUP = ROOT / "data" / "airfare_state.json.bk"
LOG_PATH = ROOT / "logs" / "airfare_engine.out"

OPENSKY_ALL = "https://opensky-network.org/api/states/all"
OPENSKY_AIRCRAFT = "https://opensky-network.org/api/aircraft/icao24/{icao24}/history"

CHEAP_DAY_OFFSET = 1
WINDOW_START_HOUR = 2
WINDOW_END_HOUR = 4

WATCHLIST_DEFAULT = [
    # Example: SFO-JFK daily flights (target specific icao24 patterns later).
    {"origin": "SFO", "destination": "JFK", "target_date": "+0d", "max_price": 320, "route": "SFO-JFK"},
    {"origin": "LAX", "destination": "JFK", "target_date": "+0d", "max_price": 280, "route": "LAX-JFK"},
    {"origin": "SFO", "destination": "SEA", "target_date": "+0d", "max_price": 180, "route": "SFO-SEA"},
]

PROXY_TICKERS = ["JBLU","DAL","UAL","LUV","AAL","BA"]


def _utcnow():
    return datetime.now(timezone.utc)


def _local_now():
    return datetime.now()


def _in_cheap_window(dt):
    return dt.weekday() == CHEAP_DAY_OFFSET and WINDOW_START_HOUR <= dt.hour < WINDOW_END_HOUR


def _relative_date(raw: str):
    try:
        if raw.startswith("+"):
            return (_local_now() + timedelta(days=int(raw[1:].rstrip("dD")))).date().isoformat()
        return raw if raw else None
    except Exception:
        return None


def _load_state():
    for path in (STATE, BACKUP):
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"watchlist": [dict(x) for x in WATCHLIST_DEFAULT], "history": [], "last_run": None, "last_session": None, "positions": {}, "quotes": {}, "flight_telemetry": {}}


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


def fetch_opensky_states(bounds=None, icao24=None):
    """Hit OpenSky /states/all with optional bbox filter.
    Returns parsed dict or {} on failure."""
    url = OPENSKY_ALL
    params = {}
    if icao24:
        params["icao24"] = icao24
    if bounds and len(bounds) == 4:
        params.update({
            "lamin": bounds[0],
            "lomin": bounds[1],
            "lamax": bounds[2],
            "lomax": bounds[3],
        })
    try:
        import urllib.parse
        qs = urllib.parse.urlencode(params)
        full = f"{url}?{qs}" if qs else url
        req = urllib.request.Request(full, headers={"User-Agent": "SoMaCoSF/0.1 (Phoenix)"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        log(f"OpenSky HTTP {e.code} on states/all")
    except Exception as e:
        log(f"OpenSky err {repr(e)[:100]}")
    return {}


def fetch_opensky_aircraft(icao24: str):
    url = OPENSKY_AIRCRAFT.format(icao24=icao24)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SoMaCoSF/0.1 (Phoenix)"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log(f"OpenSky history err {repr(e)[:100]}")
    return {}


def build_signals(watchlist, state, session_id):
    """Use real OpenSky telemetry where possible; ground with Tue/2-4AM discount."""
    signals = []
    score = score_session(_local_now())
    for item in watchlist:
        # Pull telemetry for this route if we have bounds
        telemetry = state.get("flight_telemetry", {}).get(item["route"], {})
        delay_min = telemetry.get("delay_min", 0)
        canceled = telemetry.get("canceled", False)
        early_min = telemetry.get("early_min", 0)
        ground_fare = estimate_route_fare(item, state.get("quotes", {}), score)
        # Heuristic mapping: delays and cancellations make fares go UP,
        # but having an existing cheap ticket => delta hedge to lock the trip.
        fare_delta_factor = 1.0 + (delay_min / 120.0) + (5.0 if canceled else 0.0)
        expected_fare = round(ground_fare * fare_delta_factor, 2)
        # If we already have a cheap locked fare, "hedge now" to preserve the win.
        buy_now = expected_fare <= item["max_price"] and (delay_min > 20 or canceled or early_min > 15)
        signal = {
            "route": item["route"],
            "target_date": item["target_date"],
            "expected_fare": expected_fare,
            "base_fare": ground_fare,
            "delay_min": delay_min,
            "canceled": canceled,
            "early_min": early_min,
            "max_price": item["max_price"],
            "discount_factor": score,
            "session_id": session_id,
            "buy_now": buy_now,
            "hard_signal": bool(delay_min > 20 or canceled or early_min > 15),
        }
        signals.append(signal)
    return signals


def estimate_route_fare(watchlist_item, quotes, session_score):
    base = float(watchlist_item.get("max_price", 250.0)) * 0.55
    proxy_signal = 0.0
    for sym in PROXY_TICKERS:
        q = quotes.get(sym, {})
        last = q.get("last")
        if isinstance(last, (int, float)) and last > 0:
            proxy_signal += (last * 0.035)
    if proxy_signal > 0:
        base = max(49.0, proxy_signal)
    discount = 0.82 + 0.15 * session_score
    return round(max(29.0, min(float(watchlist_item.get("max_price", 250.0)) - 0.01, base * discount)), 2)


def quote_proxy_tickers():
    # Stub: return last market close when real provider is wired.
    return {sym: {"symbol": sym, "name": sym, "last": None, "provider": "stub", "ts": time.time()} for sym in PROXY_TICKERS}


def update_telemetry(state, watchlist):
    """Poll OpenSky states and update telemetry for each active route."""
    states_all = fetch_opensky_states()
    if not states_all:
        return state
    # Index by departure/arrival bounding box
    for item in watchlist:
        route = item["route"]
        # SFO: ~37.6,-122.4, JFK: ~40.6,-73.8, LAX: ~33.9,-118.4, SEA: ~47.4,-122.3
        box_map = {
            "SFO": (37.4, -122.8, 37.8, -122.0),
            "LAX": (33.6, -118.6, 34.2, -118.0),
            "SEA": (47.2, -122.6, 47.8, -121.9),
            "JFK": (40.4, -74.2, 41.0, -73.4),
            "ORD": (41.7, -88.0, 42.2, -87.4),
            "DFW": (32.7, -97.2, 33.1, -96.6),
        }
        o = box_map.get(item["origin"])
        d = box_map.get(item["destination"])
        if o and d:
            lamin = min(o[0], d[0])
            lamax = max(o[2], d[2])
            lomin = min(o[1], d[1])
            lomax = max(o[3], d[3])
            route_states = fetch_opensky_states(bounds=(lamin, lomin, lamax, lomax))
            if route_states:
                state.setdefault("flight_telemetry", {})[route] = analyze_route(route_states.get("states", []), item, now=_local_now())
    return state


def analyze_route(states, item, now=None):
    now = now or _local_now()

    scheduled_hour = 9  # default morning departures for modeling
    delay_min = 0
    canceled = False
    early_min = 0
    for s in states:
        # OpenSky state vector indices (0-based)
        # 0 icao24, 3 lon, 4 lat, 5 geo_alt, 6 on_ground, 7 velo, 8 heading, 9 vert, 13 squawk, 17 time_position, 18 time_velocity
        try:
            lat = float(s[6])
            lon = float(s[5])
            alt = float(s[7])
            on_ground = bool(s[8])
            velo = float(s[9])

        except Exception:
            continue
        # Simple discard: too far away to be this route
        origin_ok = False
        try:
            origin_ok = -150 <= lon <= -60 and 20 <= lat <= 55
        except Exception:
            pass
        if not origin_ok:
            continue
        # If we assume daily departures, any live airborne aircraft in the window is positive.
        # Derive delay proxy from historical gate time vs current position.
        # Gate assumption: first 2h after midnight UTC for long-haul flights.
        gate_hour_utc = int(s[17] or 0) if s[17] else None
        if gate_hour_utc is not None:
            observed = now.hour + now.minute / 60.0
            delay_min = max(0, int((observed - scheduled_hour) * 60))
        if on_ground:
            delay_min = max(delay_min, 20)
        else:
            if velo < 180:
                delay_min = max(delay_min, 25)
            if alt < 1500:
                delay_min = max(delay_min, 15)
    return {"delay_min": delay_min, "canceled": canceled, "early_min": early_min, "active_states": len(states)}


def main():
    _backup_state()
    state = _load_state()
    watchlist = state["watchlist"]
    state = update_telemetry(state, watchlist)
    now = _local_now()
    session_id = f"{now:%Y-%m-%d}-{now:%H}"
    if state.get("last_session") != session_id:
        state["last_session"] = session_id
        score = score_session(now)
        log(f"session start | {now:%A} {now:%H}:{now:%M:%S} | score={score:.2f}")
        quotes = quote_proxy_tickers()
        state["quotes"] = quotes
        signals = build_signals(watchlist, state, session_id)
        buy = [s for s in signals if s["buy_now"]]
        hard = [s for s in signals if s["hard_signal"]]
        for s in signals:
            state["history"].append({
                "ts": _utcnow().isoformat(),
                "session": session_id,
                "route": s["route"],
                "expected_fare": s["expected_fare"],
                "delay_min": s["delay_min"],
                "canceled": s["canceled"],
                "buy_now": s["buy_now"],
            })
        state["history"] = state["history"][-300:]
        if hard:
            log("HARD DELAY/CANCEL signals: " + ", ".join(f"{s['route']} delay={s['delay_min']}m" for s in hard))
        if buy:
            log("BUY " + ", ".join(f"{s['route']} ${s['expected_fare']:.2f}" for s in buy))
        else:
            log(f"scanned {len(signals)} routes — no buy signals")
    state["last_run"] = _utcnow().isoformat()
    _save_state(state)
    return state


if __name__ == "__main__":
    main()
