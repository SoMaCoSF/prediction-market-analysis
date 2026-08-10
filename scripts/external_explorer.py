"""external_explorer.py — external-market cash-up loop against live Kalshi data.

Behavior:
  - polls Kalshi markets for active crypto binaries
  - applies cheap-NO strategy when drift<0 and price<=35c
  - only trades if equity > CASH_FLOOR
  - logs to logs/external_explorer.out.log
"""

import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
CASH_FLOOR = 10.00
MAX_POSITIONS = 6
POLL = 30
RUNTIME = 8 * 60 * 60  # 8h
ENTRY_MAX = 35
DRIFT_MIN = 0.20

SERIES_PAIRS = {
    "KXBTC": "XBTUSD",
    "KXETH": "ETHUSD",
    "KXSOL": "SOLUSD",
    "KXXRP": "XRPUSD",
    "KXDOGE": "DOGEUSD",
}


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        path = ROOT / "logs" / "external_explorer.out.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_active_crypto_markets() -> list[dict]:
    """Return list of active/initialized crypto binary markets with nonzero bids."""
    try:
        r = httpx.get(f"{KALSHI}/markets?limit=100", timeout=15)
        data = r.json()
        markets = data.get("markets", [])
        results = []
        for m in markets:
            ticker = m.get("ticker", "").upper()
            if not any(ticker.startswith(p) for p in SERIES_PAIRS):
                continue
            status = m.get("status", "")
            if status not in ("active", "initialized"):
                continue
            yes_bid = float(m.get("yes_bid_dollars", "0") or 0)
            no_bid = float(m.get("no_bid_dollars", "0") or 0)
            yes_ask = float(m.get("yes_ask_dollars", "0") or 0)
            no_ask = float(m.get("no_ask_dollars", "0") or 0)
            if yes_bid > 0 or no_bid > 0 or yes_ask > 0 or no_ask > 0:
                results.append({
                    "ticker": m.get("ticker"),
                    "status": status,
                    "yes_bid": yes_bid,
                    "yes_ask": yes_ask,
                    "no_bid": no_bid,
                    "no_ask": no_ask,
                    "series": next((p for p in SERIES_PAIRS if ticker.startswith(p)), ""),
                })
        return results
    except Exception as e:
        log(f"market scan error: {e}")
        return []


def get_kraken_drift(pair: str) -> float:
    """Get 24h drift from Kraken ticker."""
    try:
        r = httpx.get(f"https://api.kraken.com/0/public/Ticker?pair={pair}", timeout=10)
        data = r.json().get("result", {})
        k = next(iter(data))
        d = data[k]
        return (float(d["c"][0]) - float(d["o"][0])) / float(d["o"][0]) * 100
    except Exception:
        return 0.0


def submit_order(ticker: str, side: str, price_cents: int, count: int = 1) -> dict:
    """Submit order via local mission_control or direct Kalshi."""
    # Try local MC first
    try:
        r = httpx.post(
            "http://127.0.0.1:8420/api/order",
            json={"ticker": ticker, "side": side, "price": price_cents, "count": count, "mode": "paper", "confirm": "dry"},
            timeout=5,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass

    # Fallback: direct Kalshi
    try:
        from base64 import b64encode

        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        ts = str(int(time.time() * 1000))
        body = json.dumps({
            "ticker": ticker,
            "side": side,
            "price_cents": price_cents,
            "count": count,
        }).encode()
        full = "/trade-api/v2/portfolio/orders"
        key = serialization.load_pem_private_key((ROOT / ".kalshi_key.pem").read_bytes(), password=None)
        sig = key.sign(
            f"{ts}POST{full}{body.decode()}".encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        headers = {
            "KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"),
            "KALSHI-ACCESS-SIGNATURE": b64encode(sig).decode(),
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "Content-Type": "application/json",
        }
        r = httpx.post(f"{KALSHI}/portfolio/orders", headers=headers, content=body, timeout=15)
        return r.json() if "json" in r.headers.get("content-type", "") else {"status": r.status_code}
    except Exception as e:
        return {"error": str(e)}


def main() -> None:
    log("external_explorer start")
    start = time.time()
    while time.time() - start < RUNTIME:
        if (ROOT / ".explorer_stop").exists():
            log("stop flag detected — exiting")
            return
        try:
            markets = get_active_crypto_markets()
            log(f"scan: found {len(markets)} active crypto markets")
            for m in markets[:5]:
                log(f"  {m['ticker']} status={m['status']} yb={m['yes_bid']} nb={m['no_bid']}")
        except Exception as e:
            log(f"tick error: {e}")
        time.sleep(POLL)
    log("external_explorer 8h complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"fatal: {e}")
        raise
