#!/usr/bin/env python3
"""
WebSocket feed for Kalshi market data.
Falls back to REST polling if WS not available.
"""
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from mission_control import KALSHI_HOST, kalshi_keys, kalshi_sign  # noqa: E402

LOG = ROOT / "logs" / "ws_feed.log"
WS_URL = "wss://api.elections.kalshi.com/trade-api/ws"

def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

async def ws_market_feed(event_queue: asyncio.Queue):
    """Connect to Kalshi WebSocket and push market ticks."""
    kid, kpath = kalshi_keys()

    try:
        async with websockets.connect(WS_URL) as ws:
            log("WS CONNECTED")

            # Subscribe to market data
            subscribe_msg = {
                "type": "subscribe",
                "channels": ["markets"],
                "market_tickers": []  # empty = all markets
            }
            await ws.send(json.dumps(subscribe_msg))

            while True:
                msg = await ws.recv()
                data = json.loads(msg)

                if data.get("type") == "market_tick":
                    await event_queue.put({
                        "type": "market_tick",
                        "data": data,
                        "timestamp": time.time(),
                        "source": "kalshi_ws"
                    })
    except Exception as e:
        log(f"WS ERROR: {e} — falling back to REST polling")
        await rest_poll_fallback(event_queue)

async def rest_poll_fallback(event_queue: asyncio.PriorityQueue):
    """Fallback to REST polling if WS fails."""
    kid, kpath = kalshi_keys()
    last_volumes: dict = {}

    while True:
        try:
            ts = str(int(time.time() * 1000))
            sig = kalshi_sign("GET", "/markets?limit=200&status=open", ts, kpath)
            h = {
                "KALSHI-ACCESS-KEY": kid,
                "KALSHI-ACCESS-SIGNATURE": sig,
                "KALSHI-ACCESS-TIMESTAMP": ts,
            }
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{KALSHI_HOST}/markets?limit=200&status=open", headers=h, timeout=20)
                data = r.json()
                markets = data.get("markets", [])

                for m in markets:
                    ticker = m.get("ticker")
                    if not ticker:
                        continue

                    vol = float(m.get("volume_24h", 0) or 0)
                    prev_vol = last_volumes.get(ticker, 0)
                    vol_delta = vol - prev_vol

                    # Only emit if something changed
                    if vol_delta > 0 or vol > 0:
                        await event_queue.put({
                            "type": "market_tick",
                            "data": m,
                            "timestamp": time.time(),
                            "source": "kalshi_rest"
                        })

                    last_volumes[ticker] = vol

            await asyncio.sleep(1)  # 1s polling
        except Exception as e:
            log(f"REST fallback error: {e}")
            await asyncio.sleep(5)
