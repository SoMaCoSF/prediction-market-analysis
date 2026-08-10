#!/usr/bin/env python3
"""Volume watchdog for Kalshi.

Polls /markets every 60s. When any open market shows volume_24h > 0,
arms micro_trader.py. Stays quiet otherwise.
"""
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402
from mission_control import KALSHI_HOST, kalshi_keys, kalshi_sign  # noqa: E402

load_dotenv(ROOT / ".env")

TRADER = ROOT / "scripts" / "micro_trader.py"
PYTHON = ROOT / ".venv311" / "Scripts" / "python.exe"
LOCK = ROOT / "logs" / ".volume_watchdog.lock"
LOG = ROOT / "logs" / "volume_watchdog.log"
POLL = 60


def log(msg: str) -> None:
    line = f"[{datetime.utcnow().isoformat()}Z] {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(exist_ok=True)
        with LOG.open("a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def is_trader_running() -> bool:
    try:
        r = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {Path(PYTHON).name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10
        )
        for line in r.stdout.splitlines():
            if "python.exe" in line.lower():
                # Check if it's actually running micro_trader
                r2 = subprocess.run(
                    ["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine", "/FORMAT:CSV"],
                    capture_output=True, text=True, timeout=10
                )
                for row in r2.stdout.splitlines():
                    if "micro_trader" in row.lower():
                        return True
    except Exception:
        pass
    return False


def arm_trader() -> None:
    if is_trader_running():
        log("trader already running, skip arm")
        return
    log("VOLUME DETECTED — arming micro_trader.py")
    try:
        subprocess.Popen(
            [str(PYTHON), str(TRADER)],
            cwd=str(ROOT),
            stdout=open(ROOT / "logs" / "micro_trader_watchdog.out", "a"),
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
        log("trader armed successfully")
    except Exception as e:
        log(f"arm ERR: {e}")


def check_volume() -> bool:
    try:
        kid, kpath = kalshi_keys()
        ts = str(int(time.time() * 1000))
        sig = kalshi_sign("GET", "/markets", ts, kpath)
        h = {
            "KALSHI-ACCESS-KEY": kid,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "KALSHI-ACCESS-TIMESTAMP": ts,
        }
        r = httpx.get(
            f"{KALSHI_HOST}/markets",
            params={"limit": 200, "status": "open"},
            headers=h,
            timeout=20,
        )
        r.raise_for_status()
        markets = r.json().get("markets", [])
        alive = [m for m in markets if float(m.get("volume_24h", 0) or 0) > 0]
        if alive:
            best = max(alive, key=lambda m: float(m.get("volume_24h", 0) or 0))
            log(f"ALIVE: {len(alive)} markets with volume, best={best.get('ticker')} vol={best.get('volume_24h')}")
            return True
        return False
    except Exception as e:
        log(f"check ERR: {e}")
        return False


def main() -> None:
    # Self-singleton
    try:
        if LOCK.exists():
            old_pid = LOCK.read_text().strip()
            if old_pid and old_pid.isdigit():
                import psutil
                try:
                    p = psutil.Process(int(old_pid))
                    cmd = " ".join(p.cmdline()).lower()
                    if "volume_watchdog" in cmd:
                        log(f"another watchdog running (pid {old_pid}) — exiting")
                        return
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
    except Exception:
        pass
    try:
        LOCK.write_text(str(os.getpid()))
    except Exception:
        pass

    log("volume_watchdog starting (Kalshi auto-arm on liquidity)")
    while True:
        try:
            if check_volume():
                arm_trader()
            else:
                log("no volume, sleeping 60s")
        except Exception as e:
            log(f"loop ERR: {e}")
        time.sleep(POLL)


if __name__ == "__main__":
    main()
