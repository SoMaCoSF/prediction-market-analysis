#!/usr/bin/env python3
"""
market_scanner.py

Continuous market scanner for Kalshi.
  - Polls /markets?limit=200&status=open every 60s.
  - Records ANY market with non-zero bid/ask/volume to a JSONL log.
  - No orders placed — pure intelligence gathering.
  - Output: data/market_scan.jsonl
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import mission_control as mc
except Exception as e:
    print("FATAL: cannot import mission_control:", e)
    sys.exit(1)

LOG_PATH = ROOT / "data" / "market_scan.jsonl"
BACKUP_PATH = ROOT / "data" / "market_scan.jsonl.bk"
POLL_INTERVAL = 60


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def log(msg: str):
    line = f"[{_utcnow()}] [market_scanner] {msg}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _direct_get(path: str):
    import urllib.request
    kid, kpath = mc.kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = mc.kalshi_sign("GET", path, ts, kpath)
    req = urllib.request.Request(
        f"{mc.KALSHI_HOST}{path}",
        headers={
            "KALSHI-ACCESS-KEY": kid,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "KALSHI-ACCESS-TIMESTAMP": ts,
        },
    )
    return json.loads(urllib.request.urlopen(req).read())


def scan_once():
    """Scan all open markets and log any with liquidity."""
    try:
        data = _direct_get("/markets?limit=200&status=open")
        markets = data.get("markets", [])
    except Exception as e:
        log(f"scan err: {repr(e)}")
        return

    liquid = []
    for m in markets:
        ticker = m.get("ticker", "")
        if not ticker:
            continue
        yes_bid = float(m.get("yes_bid_dollars") or 0)
        yes_ask = float(m.get("yes_ask_dollars") or 0)
        no_bid = float(m.get("no_bid_dollars") or 0)
        no_ask = float(m.get("no_ask_dollars") or 0)
        vol = float(m.get("volume_24h") or 0)

        if vol > 0 or (yes_bid > 0 and yes_bid < 1) or (yes_ask > 0 and yes_ask < 1) or (no_bid > 0 and no_bid < 1) or (no_ask > 0 and no_ask < 1):
            liquid.append({
                "ts": _utcnow(),
                "ticker": ticker,
                "yes_bid": yes_bid,
                "yes_ask": yes_ask,
                "no_bid": no_bid,
                "no_ask": no_ask,
                "volume": vol,
                "event_ticker": m.get("event_ticker", ""),
                "title": m.get("title", ""),
            })

    if liquid:
        log(f"found {len(liquid)} liquid markets")
        try:
            line = json.dumps({"ts": _utcnow(), "markets": liquid})
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            BACKUP_PATH.write_text(line, encoding="utf-8")
        except Exception as e:
            log(f"write err: {repr(e)}")
    else:
        log("no liquid markets this pass")


def main():
    log("market_scanner starting")
    try:
        while True:
            scan_once()
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        log("shutting down")


if __name__ == "__main__":
    main()
