#!/usr/bin/env python3
"""Update mc_state with live Kalshi portfolio data."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import httpx  # noqa: E402
import sb  # noqa: E402
from mission_control import KALSHI_HOST, kalshi_keys, kalshi_sign  # noqa: E402

con = sb.sb_conn()
cur = con.cursor()

# Get live balance + positions from Kalshi
kid, kpath = kalshi_keys()
ts = str(int(time.time() * 1000))
sig = kalshi_sign("GET", "/portfolio/balance", ts, kpath)
h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}
r = httpx.get(f"{KALSHI_HOST}/portfolio/balance", headers=h, timeout=20)
balance_data = r.json()

ts2 = str(int(time.time() * 1000))
sig2 = kalshi_sign("GET", "/portfolio/positions", ts2, kpath)
h2 = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig2, "KALSHI-ACCESS-TIMESTAMP": ts2}
r2 = httpx.get(f"{KALSHI_HOST}/portfolio/positions", headers=h2, timeout=20)
positions_data = r2.json().get("market_positions", [])

# Update mc_state with live data
state = {
    "ts": time.time(),
    "cash": float(balance_data.get("balance_dollars", 0)),
    "account_equity": float(balance_data.get("portfolio_value", 0)),
    "positions": [{"ticker": p.get("ticker"), "fp": float(p.get("position_fp") or 0)} for p in positions_data],
    "open_count": len(positions_data),
    "floor_hit": float(balance_data.get("balance_dollars", 0)) < 1.00,
    "paused": False,
    "alerts": [],
    "daemons": {},
    "actions": [],
}
cur.execute("UPDATE mc_state SET v=%s WHERE k=%s", (json.dumps(state), "watcher:state"))
con.commit()
con.close()

print("mc_state updated with live data")
print(f"cash=${state['cash']:.4f} equity=${state['account_equity']:.2f} positions={state['open_count']}")
