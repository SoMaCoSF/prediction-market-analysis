# file_id: SOM-PY-0936-v1.0.0 name: uuid_ingest.py description: Signal ingest — mint every raw tick (Kalshi book mid + crypto spot) as a GYST UUID into a local stream store; deterministic dedupe; algos consume UUIDs not JSON project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [ingest, signals, uuid, stream, tape] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""uuid_ingest.py — the tape-to-UUID edge.

Every tick becomes a self-describing signal UUID:
  Kalshi book mid  -> 0x3A1 QUOTE   (ns=fnv1a12(market uuid), signal=mid, prov=KALSHI)
  Crypto spot      -> 0x3C0 SPOT    (ns=fnv1a12('spot:<SYM>'), signal=scaled price bps, prov=DEXTER)

Deterministic content seed = the payload, so identical ticks mint identical UUIDs
and dedupe for free (INSERT OR IGNORE). Store = local SQLite (data/uuid_stream.db,
gitignored). No LLM in the path: zero tokens, pure HTTP+CPU.

Downstream: algos filter the stream by bitmask ((uuid_hi>>52)&4095 = type,
namespace match = symbol) instead of parsing JSON.
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import httpx  # noqa: E402
import runlog  # noqa: E402
import uuid_ledger as L  # noqa: E402
from uuid_service_turboquant import encode_gyst, fnv1a12  # noqa: E402

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
DB = ROOT / "data" / "uuid_stream.db"
POLL_S = 5

TYPE_QUOTE = 0x3A1
TYPE_SPOT = 0x3C0
PROV_KALSHI = 0x9
PROV_SPOT = 0x1   # DEXTER/external tape

SERIES = ["KXBTC15M", "KXETH15M", "KXSOL15M", "KXXRP15M", "KXDOGE15M"]
SPOT = [("XBTUSD", "BTC"), ("ETHUSD", "ETH"), ("SOLUSD", "SOL"), ("XRPUSD", "XRP"), ("DOGEUSD", "DOGE")]


def db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS stream(
        uuid TEXT PRIMARY KEY, ts INT, source TEXT, symbol TEXT,
        price_c REAL, uuid_hi INT, uuid_lo INT)""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_stream_ts ON stream(ts)")
    return con


def mint_quote(market_uuid: str, mid_c: float, ts: int):
    u = encode_gyst(type_code=TYPE_QUOTE, namespace=fnv1a12(market_uuid), timestamp_sec=ts,
                    fractal_depth=1, fractal_domain=0x1, fractal_generation=1,
                    forecast_signal=mid_c / 100.0, provenance=PROV_KALSHI,
                    content_seed=f"quote|{market_uuid}|{mid_c:.2f}|{ts}")
    return u


def mint_spot(sym: str, px: float, ts: int):
    # signal carries price in basis points of $100k for BTC-scale assets, raw for small caps
    scaled = min(1.0, px / 100000.0) if px > 100 else min(1.0, px / 1000.0)
    u = encode_gyst(type_code=TYPE_SPOT, namespace=fnv1a12(f"spot:{sym}"), timestamp_sec=ts,
                    fractal_depth=0, fractal_domain=0x6, fractal_generation=0,
                    forecast_signal=scaled, provenance=PROV_SPOT,
                    content_seed=f"spot|{sym}|{px}|{ts}")
    return u


def main():
    fleetlib.acquire_lock("ingest")
    con = db()
    cur = con.cursor()
    n = 0
    print(f"[ingest] start -> {DB} (poll {POLL_S}s, zero tokens)", flush=True)
    with httpx.Client(headers={"Accept-Encoding": "identity"}, timeout=15) as cx:
        while True:
            fleetlib.checkin("ingest")
            ts = int(time.time())
            for series in SERIES:
                try:
                    r = cx.get(f"{KALSHI}/markets", params={"limit": 5, "status": "open", "series_ticker": series})
                    for m in r.json().get("markets", []):
                        ya = m.get("yes_ask_dollars")
                        yb = m.get("yes_bid_dollars")
                        if ya is None or yb is None:
                            continue
                        mid = round((float(ya) + float(yb)) / 2 * 100, 2)
                        if mid <= 0:
                            continue
                        mu = L.mint_market_uuid(m["ticker"])
                        u = mint_quote(mu, mid, ts)
                        hi, lo = L.hi_lo(u)
                        cur.execute("INSERT OR IGNORE INTO stream VALUES (?,?,?,?,?,?,?)",
                                    (u, ts, "kalshi", m["ticker"], mid, hi, lo))
                        n += cur.rowcount
                except Exception:
                    pass
            for pair, sym in SPOT:
                try:
                    d = cx.get(f"https://api.kraken.com/0/public/Ticker?pair={pair}").json()["result"]
                    k = next(iter(d))
                    px = float(d[k]["c"][0])
                    u = mint_spot(sym, px, ts)
                    hi, lo = L.hi_lo(u)
                    cur.execute("INSERT OR IGNORE INTO stream VALUES (?,?,?,?,?,?,?)",
                                (u, ts, "spot", sym, px, hi, lo))
                    n += cur.rowcount
                except Exception:
                    pass
            con.commit()
            if ts % 60 < POLL_S:
                cur.execute("SELECT count(*) FROM stream")
                total = cur.fetchone()[0]
                print(f"[ingest] {time.strftime('%H:%M:%S')} stream_rows={total} (+{n} new)", flush=True)
                runlog.log_event("ingest", f"stream_rows={total} (+{n} new)", rows=total, new=n)
                n = 0
            time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
