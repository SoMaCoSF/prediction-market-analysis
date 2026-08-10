#!/usr/bin/env python3
"""Kalshi 24h cycle daemon — 5-min position scan, hourly summary."""
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
from mission_control import KALSHI_HOST, kalshi_keys, kalshi_sign

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / ".env")

LOG = ROOT / "logs" / "cycle_daemon.log"
LOG.parent.mkdir(exist_ok=True)


def log(msg: str) -> None:
    line = f"[{datetime.utcnow().isoformat()}Z] {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def main() -> None:
    kid, kpath = kalshi_keys()
    host = KALSHI_HOST
    last_hourly = time.time()
    log(f"cycle daemon started pid={os.getpid()}")

    while True:
        try:
            now = time.time()
            ts = str(int(now * 1000))
            sig = kalshi_sign("GET", "/portfolio/positions", ts, kpath)
            h = {
                "KALSHI-ACCESS-KEY": kid,
                "KALSHI-ACCESS-SIGNATURE": sig,
                "KALSHI-ACCESS-TIMESTAMP": ts,
            }
            r = httpx.get(f"{host}/portfolio/positions", headers=h, timeout=20)
            r.raise_for_status()
            positions = r.json().get("market_positions", [])

            for mp in positions:
                pos_fp = float(mp.get("position_fp") or 0)
                if pos_fp == 0:
                    continue
                ticker = mp.get("ticker")
                current = float(mp.get("last_price") or 0) * 100
                side = "YES" if pos_fp > 0 else "NO"
                log(f"POS {ticker} {side} qty={pos_fp:.0f} current={current:.0f}c")

            if now - last_hourly >= 3600:
                last_hourly = now
                active = [mp for mp in positions if float(mp.get("position_fp") or 0) != 0]
                exposure = sum(float(mp.get("market_exposure_dollars") or 0) for mp in active)
                log(f"HOURLY active={len(active)} exposure=${exposure:.2f}")

        except Exception as e:
            log(f"ERR {repr(e)[:200]}")
            traceback.print_exc()
        time.sleep(60)


if __name__ == "__main__":
    main()
