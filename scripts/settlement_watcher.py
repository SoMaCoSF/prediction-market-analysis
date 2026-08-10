#!/usr/bin/env python3
"""
Settlement watcher daemon — polls all open positions and alerts when
markets approach close_time or resolution changes.

Runs every 5 minutes, logs to logs/settlement_watcher.out.
"""
import os, sys, time, json
from pathlib import Path
from datetime import datetime, timezone, timedelta

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from mission_control import KALSHI_HOST, kalshi_keys, kalshi_sign

LOG = ROOT / "logs" / "settlement_watcher.out"
ALERT_HOURS = 24  # alert if market closes within 24h
POLL_INTERVAL = 300  # 5 minutes


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
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


def parse_dt(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def run_once():
    try:
        positions_data = signed_get("/portfolio/positions")
        positions = positions_data.get("event_positions", [])
    except Exception as e:
        log(f"ERROR fetching positions: {e}")
        return

    now = datetime.now(timezone.utc)
    alerts = []

    for pos in positions:
        event_ticker = pos.get("event_ticker")
        total_cost = float(pos.get("total_cost_dollars", 0))
        shares = float(pos.get("total_cost_shares_fp", 0))

        # Find markets for this event
        try:
            markets_data = signed_get(f"/markets?limit=50&status=open&event_ticker={event_ticker}")
            markets = markets_data.get("markets", [])
        except Exception:
            markets = []

        for m in markets:
            ticker = m.get("ticker")
            close_time = parse_dt(m.get("close_time"))
            status = m.get("status", "unknown")
            yes_bid = float(m.get("yes_bid_dollars", 0) or 0)
            yes_ask = float(m.get("yes_ask_dollars", 0) or 0)

            # Alert if closing soon
            if close_time:
                hours_to_close = (close_time - now).total_seconds() / 3600
                if 0 < hours_to_close <= ALERT_HOURS:
                    alerts.append({
                        "event": event_ticker,
                        "ticker": ticker,
                        "shares": shares,
                        "cost": total_cost,
                        "close_time": close_time.isoformat(),
                        "hours_to_close": round(hours_to_close, 1),
                        "yes_bid_cents": round(yes_bid * 100, 2),
                        "yes_ask_cents": round(yes_ask * 100, 2),
                        "status": status,
                    })

            # Alert if market already settled/resolved
            if status in ("settled", "resolved", "closed"):
                alerts.append({
                    "event": event_ticker,
                    "ticker": ticker,
                    "shares": shares,
                    "cost": total_cost,
                    "status": status,
                    "resolution": m.get("resolution"),
                })

    if alerts:
        log(f"SETTLEMENT ALERTS: {len(alerts)} markets need attention")
        for a in alerts:
            log(f"  {a['ticker'][:60]} | {a.get('hours_to_close', '?')}h to close | bid={a.get('yes_bid_cents', '?')}¢ | status={a['status']}")
    else:
        log(f"Checked {len(positions)} positions — no imminent settlements")


def main():
    log("SETTLEMENT WATCHER STARTED")
    log(f"Polling every {POLL_INTERVAL}s, alerting {ALERT_HOURS}h before close")
    while True:
        try:
            run_once()
        except Exception as e:
            log(f"ERROR: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
