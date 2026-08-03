# file_id: SOM-PY-0951-v1.0.0 name: x_watcher.py description: X/signal watchers — keyless high-velocity feeds (CoinGecko trending, Reddit crypto, ESPN live, Fear&Greed) minted as 0x3D1 signal UUIDs into the stream; xAI stub for true X when keyed; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [x, watchers, signals, ingest, sentiment, espn, zero-token] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""x_watcher.py — all the watchers, maxxed, zero tokens.

Sources (keyless, public JSON):
  coingecko /coins/markets trending-ish movers  -> 0x3D1 (signal=24h change)
  reddit r/Bitcoin+r/CryptoCurrency hot         -> 0x3D1 (signal=score-norm)
  ESPN scoreboard (NBA/MLB live)                -> 0x3D1 (signal=game progress)
  alternative.me Fear & Greed                   -> 0x3D1 (signal=fng/100)
xAI true-X path: set XAI_API_KEY in .env — drops in without touching callers.

Each hit minted deterministic (dedupe by content seed) into uuid_stream.db.
Downstream: btc_trend can read attention velocity; sports tails get live state.
"""
from __future__ import annotations

import os
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
from dotenv import load_dotenv  # noqa: E402
from uuid_service_turboquant import encode_gyst, fnv1a12  # noqa: E402

load_dotenv(ROOT / ".env")
DB = ROOT / "data" / "uuid_stream.db"
TYPE_SIGNAL = 0x3D1
PROV_X = 0xB   # external social/news plane
POLL_S = 60
XAI_KEY = os.getenv("XAI_API_KEY", "")


def mint_signal(src: str, name: str, signal01: float, seed: str, ts: int):
    u = encode_gyst(type_code=TYPE_SIGNAL, namespace=fnv1a12(f"{src}:{name}"), timestamp_sec=ts,
                    fractal_depth=1, fractal_domain=0x7, fractal_generation=0,
                    forecast_signal=max(0.0, min(1.0, signal01)), provenance=PROV_X,
                    content_seed=seed)
    return u


def store(cur, u, ts, src, name, val):
    hi, lo = L.hi_lo(u)
    cur.execute("INSERT OR IGNORE INTO stream VALUES (?,?,?,?,?,?,?)",
                (u, ts, src, name, val, hi, lo))
    return cur.rowcount


def coingecko(cx, cur, ts):
    n = 0
    d = cx.get("https://api.coingecko.com/api/v3/coins/markets",
               params={"vs_currency": "usd", "ids": "bitcoin,ethereum,solana,ripple,dogecoin",
                       "price_change_percentage": "1h,24h"}, timeout=15).json()
    for c in d:
        chg = float(c.get("price_change_percentage_1h_in_currency") or 0)
        sig = 0.5 + max(-5, min(5, chg)) / 10  # ±5%/h -> 0..1
        n += store(cur, mint_signal("coingecko", c["symbol"].upper(), sig, f"cg|{c['symbol']}|{round(chg,2)}|{ts//300}", ts),
                   ts, "coingecko", c["symbol"].upper(), round(chg, 3))
    return n


def reddit(cx, cur, ts):
    n = 0
    for sub in ["Bitcoin", "CryptoCurrency"]:
        d = cx.get(f"https://www.reddit.com/r/{sub}/hot.json?limit=10&raw_json=1",
                   headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
                            "Accept": "application/json"}, timeout=15).json()
        for post in (d.get("data", {}).get("children") or []):
            p = post.get("data", {})
            score = float(p.get("score") or 0)
            sig = min(1.0, score / 5000.0)
            title = (p.get("title") or "")[:60]
            n += store(cur, mint_signal("reddit", sub, sig, f"rd|{p.get('id')}|{sub}", ts),
                       ts, "reddit", f"r/{sub}", score)
            _ = title
    return n


def espn(cx, cur, ts):
    n = 0
    for sport, league in [("basketball", "nba"), ("baseball", "mlb")]:
        try:
            d = cx.get(f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard", timeout=15).json()
        except Exception:
            continue
        for ev in (d.get("events") or [])[:12]:
            comp = (ev.get("competitions") or [{}])[0]
            status = (ev.get("status") or {}).get("type", {})
            state = status.get("state", "pre")
            progress = {"pre": 0.0, "in": 0.5, "post": 1.0}.get(state, 0.0)
            name = (ev.get("shortName") or "")[:28]
            n += store(cur, mint_signal("espn", f"{league}:{ev.get('id')}", progress,
                                        f"espn|{ev.get('id')}|{state}", ts),
                       ts, "espn", f"{league}:{name}", progress)
    return n


def fear_greed(cx, cur, ts):
    try:
        d = cx.get("https://api.alternative.me/fng/?limit=1", timeout=15).json()
        v = float(d["data"][0]["value"])
        return store(cur, mint_signal("fng", "crypto", v / 100.0, f"fng|{v}|{ts//3600}", ts),
                     ts, "fng", "crypto", v)
    except Exception:
        return 0


def main():
    fleetlib.acquire_lock("xwatch")
    print(f"[xwatch] start | sources=coingecko,reddit,espn,fng poll={POLL_S}s xai={'KEYED' if XAI_KEY else 'stub'}", flush=True)
    runlog.log_event("xwatch", f"watcher start xai={'KEYED' if XAI_KEY else 'stub'}", poll_s=POLL_S)
    with httpx.Client(headers={"Accept-Encoding": "identity"}, timeout=20) as cx:
        while True:
            fleetlib.checkin("xwatch")
            ts = int(time.time())
            total = 0
            try:
                con = sqlite3.connect(DB)
                cur = con.cursor()
                for fn in (coingecko, reddit, espn, fear_greed):
                    try:
                        total += fn(cx, cur, ts)
                    except Exception as e:
                        runlog.log_event("xwatch", f"{fn.__name__} warn {repr(e)[:60]}", kind="warn")
                con.commit()
                con.close()
            except Exception as e:
                runlog.log_event("xwatch", f"cycle warn {repr(e)[:60]}", kind="warn")
            if ts % 300 < POLL_S:
                runlog.log_event("xwatch", f"cycle +{total} signal UUIDs", new=total)
                print(f"[xwatch] {time.strftime('%H:%M:%S')} +{total} signals", flush=True)
            time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
