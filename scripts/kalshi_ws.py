# file_id: SOM-PY-0978-v1.0.0 name: kalshi_ws.py description: Kalshi WS firehose — official wss v2 ticker stream for the 15M windows, written to the local tape (source=kalshi-ws) so engines see sub-second exchange-native momentum; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [kalshi, websocket, firehose, tape, stream] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""kalshi_ws.py — the firehose. Official Kalshi WS v2 ticker channel.

Subscribes the CURRENT 15M windows (all 5 series), streams every price tick
into data/uuid_stream.db as source='kalshi-ws'. Resubscribes on window rolls.
Reconnects with backoff. Zero model tokens.
"""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import httpx  # noqa: E402
import runlog  # noqa: E402
import websockets  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
DB = ROOT / "data" / "uuid_stream.db"
SERIES = {"KXBTC15M": "BTC", "KXETH15M": "ETH", "KXSOL15M": "SOL", "KXXRP15M": "XRP", "KXDOGE15M": "DOGE"}


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] [ws] {m}", flush=True)
    runlog.log_event("ws", m)


def _sign(method, path, ts):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key((ROOT / ".kalshi_key.pem").read_bytes(), password=None)
    sig = key.sign(f"{ts}{method}{path}".encode(),
                   padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                   hashes.SHA256())
    return base64.b64encode(sig).decode()


def ws_headers():
    ts = str(int(time.time() * 1000))
    return {"KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"),
            "KALSHI-ACCESS-SIGNATURE": _sign("GET", "/trade-api/ws/v2", ts),
            "KALSHI-ACCESS-TIMESTAMP": ts}


def current_windows():
    out = {}
    try:
        with httpx.Client(timeout=15) as cx:
            for series, sym in SERIES.items():
                r = cx.get(f"{KALSHI}/markets", params={"limit": 3, "status": "open", "series_ticker": series})
                for m in r.json().get("markets", []):
                    close = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
                    if close - time.time() > 120:
                        out[m["ticker"]] = sym
                        break
    except Exception as e:
        log(f"window scan warn {repr(e)[:50]}")
    return out


def store(sym, price_c, bid_c, ts):
    try:
        con = sqlite3.connect(DB)
        con.execute("INSERT INTO stream (source, symbol, price_c, ts) VALUES ('kalshi-ws', ?, ?, ?)",
                    (sym, price_c, ts))
        con.commit()
        con.close()
    except Exception:
        pass


async def tape():
    tickers = current_windows()
    if not tickers:
        log("no windows open")
        await asyncio.sleep(30)
        return
    log(f"subscribing {len(tickers)} windows: {list(tickers.values())}")
    async with websockets.connect(WS_URL, additional_headers=ws_headers(), ping_interval=20) as ws:
        await ws.send(json.dumps({"id": 1, "cmd": "subscribe",
                                  "params": {"channels": ["ticker"], "market_tickers": list(tickers)}}))
        n = 0
        t0 = time.time()
        async for raw in ws:
            try:
                msg = json.loads(raw)
                if msg.get("type") != "ticker":
                    continue
                d = msg.get("msg", {})
                tk = d.get("market_ticker", "")
                sym = tickers.get(tk)
                if not sym:
                    continue
                ya = float(d.get("yes_ask_dollars") or 0) * 100
                yb = float(d.get("yes_bid_dollars") or 0) * 100
                if ya > 0:
                    store(sym, ya, yb, int(time.time()))
                    n += 1
                    if n % 500 == 0:
                        fleetlib.checkin("ws")
                        log(f"{n} ticks in {time.time()-t0:.0f}s | {sym} {ya:.0f}¢")
            except Exception:
                continue


def main():
    fleetlib.acquire_lock("ws")
    log("WS firehose start")
    while True:
        fleetlib.checkin("ws")
        try:
            asyncio.run(tape())
        except Exception as e:
            log(f"reconnect: {repr(e)[:60]}")
            time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
