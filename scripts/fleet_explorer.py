"""fleet_explorer.py — 8-hour aggressive cash-up loop.

Behavior:
  - polls Kalshi balance/positions every N seconds
  - only trades if equity > CASH_FLOOR
  - uses momentum lane entries
  - exits on time limit or manual flag
"""

import json
import os
import time
from base64 import b64encode
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
MC = "http://127.0.0.1:8420"
CASH_FLOOR = 10.00
MAX_LIVE_POSITIONS = 6
POLL = 20
RUNTIME = 8 * 60 * 60  # 8h


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


def submit_live(ticker: str, side: str, price_cents: int, count: int = 1) -> dict:
    try:
        payload = {
            "ticker": ticker,
            "side": side,
            "price_cents": price_cents,
            "count": count,
        }
        ts = str(int(time.time() * 1000))
        body = json.dumps(payload).encode()
        full = "/trade-api/v2/portfolio/orders"
        key = serialization.load_pem_private_key((ROOT / ".kalshi_key.pem").read_bytes(), password=None)
        sig = key.sign(
            f"{ts}POST{full}{body.decode()}".encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        h = {
            "KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"),
            "KALSHI-ACCESS-SIGNATURE": b64encode(sig).decode(),
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "Content-Type": "application/json",
        }
        r = httpx.post(KALSHI + "/portfolio/orders", headers=h, content=body, timeout=15)
        return r.json() if "json" in r.headers.get("content-type", "") else {"status": r.status_code, "text": r.text[:200]}
    except Exception as e:
        return {"error": str(e)}


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        path = ROOT / "logs" / "explorer.out.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main() -> None:
    log("fleet_explorer start")
    start = time.time()
    while time.time() - start < RUNTIME:
        if (ROOT / ".explorer_stop").exists():
            log("stop flag detected — exiting")
            return
        try:
            cash, equity = get_balance()
            positions = get_positions()
            open_count = len(positions)
            log(f"cash=${cash:.2f} equity=${equity:.2f} pos={open_count}")

            if equity <= CASH_FLOOR:
                log("floor guard active — waiting")
                time.sleep(POLL)
                continue

            if open_count >= MAX_LIVE_POSITIONS:
                log("position cap reached — waiting")
                time.sleep(POLL)
                continue

            ticker = "KXBTC15M-26AUG062045-45"
            market = kget(f"/markets/{ticker}")
            yes_bid = int(market.get("previous_yes_bid_dollars", 0) * 100)
            if yes_bid <= 0:
                log("no valid yes_bid — waiting")
                time.sleep(POLL)
                continue

            price = max(1, min(yes_bid, 99))
            res = submit_live(ticker, "yes", price, 1)
            log(f"submit {ticker} yes {price}c -> {json.dumps(res)[:180]}")
        except Exception as e:
            log(f"tick err: {e}")
        time.sleep(POLL)
    log("fleet_explorer 8h complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"fatal: {e}")
        raise
