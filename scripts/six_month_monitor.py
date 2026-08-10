"""six_month_monitor.py — passive 6-month watcher.

Behavior:
  - polls Kalshi balance/positions every N minutes
  - logs to logs/six_month_monitor.out.log
  - publishes watcher state to mc_state
  - NEVER trades
  - exits on .stop_monitor flag or 6-month timeout
"""

import json
import os
import sys
import time
from base64 import b64encode
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / ".env")

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
POLL = 600  # 10 minutes
RUNTIME = 6 * 30 * 24 * 60 * 60  # ~6 months


def kget(path: str) -> dict:
    try:
        ts = str(int(time.time() * 1000))
        full = "/trade-api/v2" + path.split("?")[0]
        key = serialization.load_pem_private_key((ROOT / ".kalshi_key.pem").read_bytes(), password=None)
        sig = key.sign(
            f"{ts}GET{full}".encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        h = {
            "KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"),
            "KALSHI-ACCESS-SIGNATURE": b64encode(sig).decode(),
            "KALSHI-ACCESS-TIMESTAMP": ts,
        }
        r = httpx.get(KALSHI + path, headers=h, timeout=15)
        return r.json() if "json" in r.headers.get("content-type", "") else {}
    except Exception:
        return {}


def get_balance() -> tuple[float, float]:
    d = kget("/portfolio/balance")
    cash = float(d.get("balance_dollars", 0))
    equity = float(d.get("portfolio_value", cash))
    return cash, equity


def get_positions() -> list[dict]:
    d = kget("/portfolio/positions") or {}
    return d.get("market_positions", []) or []


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        path = ROOT / "logs" / "six_month_monitor.out.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def publish(cash: float, equity: float, positions: list[dict]) -> None:
    try:
        import sb
        con = sb.sb_conn()
        cur = con.cursor()
        state = {
            "ts": time.time(),
            "cash": cash,
            "equity": equity,
            "positions": len(positions),
            "mode": "monitor",
        }
        cur.execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES (%s, %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=EXCLUDED.updated_at",
            ("six_month_monitor:state", json.dumps(state)),
        )
        con.commit()
        con.close()
    except Exception as e:
        log(f"publish err: {e}")


def main() -> None:
    log("six_month_monitor start")
    start = time.time()
    while time.time() - start < RUNTIME:
        if (ROOT / ".stop_monitor").exists():
            log("stop flag detected — exiting")
            return
        try:
            cash, equity = get_balance()
            positions = get_positions()
            log(f"cash=${cash:.2f} equity=${equity:.2f} positions={len(positions)}")
            publish(cash, equity, positions)
        except Exception as e:
            log(f"tick err: {e}")
        time.sleep(POLL)
    log("six_month_monitor 6-month complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"fatal: {e}")
        raise
