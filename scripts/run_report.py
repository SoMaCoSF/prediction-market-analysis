# file_id: SOM-PY-0940-v1.0.0 name: run_report.py description: Zero-token full-run reconstruction — reads JSONL run log + Supabase ledger + exchange truth, prints the entire session story in detail project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [report, runlog, observability, zero-token, summary] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""run_report.py — the whole run, in detail, in one call. No model tokens.

Usage: PYTHONPATH= .venv311/Scripts/python.exe scripts/run_report.py [--tail N]
Sources: logs/run_*.jsonl (daemon events + assertions), Supabase ledger,
Kalshi exchange truth (balance + open positions)."""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import httpx  # noqa: E402
import sb  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"


def _sign(method, path, ts):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key((ROOT / ".kalshi_key.pem").read_bytes(), password=None)
    sig = key.sign(f"{ts}{method}{path}".encode(),
                   padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                   hashes.SHA256())
    return base64.b64encode(sig).decode()


def kget(path):
    try:
        ts = str(int(time.time() * 1000))
        full = "/trade-api/v2" + path.split("?")[0]
        h = {"KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"),
             "KALSHI-ACCESS-SIGNATURE": _sign("GET", full, ts),
             "KALSHI-ACCESS-TIMESTAMP": ts}
        r = httpx.get(KALSHI + path, headers=h, timeout=15)
        return r.json() if "json" in r.headers.get("content-type", "") else {}
    except Exception:
        return {}


def read_events():
    evts = []
    for f in sorted((ROOT / "logs").glob("run_*.jsonl")):
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                evts.append(json.loads(line))
            except Exception:
                pass
    return evts


def main():
    tail = int(sys.argv[sys.argv.index("--tail") + 1]) if "--tail" in sys.argv else 40
    print("=" * 78)
    print("SOMACO UUID-TRADER — FULL RUN REPORT (zero-token reconstruction)")
    print("=" * 78)

    # ---- 1. daemon event log ----
    evts = read_events()
    print(f"\n[1] RUN LOG: {len(evts)} events across actors")
    by_actor = Counter(e.get("actor") for e in evts)
    for a, n in by_actor.most_common():
        print(f"    {a:8s} {n} events")
    asserts = [e for e in evts if e.get("kind") == "assert"]
    fails = [e for e in asserts if not e.get("pass")]
    print(f"    assertions: {len(asserts)} total, {len(fails)} FAILED")
    for e in fails[:10]:
        print(f"    !! FAIL {e.get('t')} [{e.get('actor')}] {e.get('msg')}")

    print(f"\n[2] EVENT TIMELINE (last {tail})")
    for e in evts[-tail:]:
        extra = ""
        if e.get("kind") == "assert":
            extra = " ASSERT:" + ("PASS" if e.get("pass") else "FAIL")
        print(f"    {e.get('t')} [{e.get('actor','?'):6s}]{extra} {e.get('msg')}")

    # ---- 2. ledger (Supabase) ----
    print("\n[3] LEDGER (Supabase SoT)")
    try:
        con = sb.sb_conn()
        cur = con.cursor()
        for tbl in ["uuid_orders", "uuid_acks", "uuid_fills", "uuid_positions"]:
            cur.execute(f"SELECT count(*) FROM {tbl}")
            print(f"    {tbl:16s} {cur.fetchone()[0]} rows")
        cur.execute("SELECT coalesce(sum(realized_pnl_cents),0) FROM uuid_positions")
        print(f"    realized P&L: {cur.fetchone()[0]}c")
        cur.execute("""SELECT ticker, side, price_cents, count, status, to_char(created_at,'HH24:MI:SS')
                       FROM uuid_orders WHERE mode='live' ORDER BY created_at DESC LIMIT 12""")
        print("    last 12 live orders:")
        for r in cur.fetchall():
            print(f"      {r[5]} {r[0][:40]:40s} {r[1]:3s} {r[2]}c x{r[3]} {r[4]}")
        con.close()
    except Exception as e:
        print(f"    ledger read failed: {repr(e)[:80]}")

    # ---- 3. exchange truth ----
    print("\n[4] EXCHANGE TRUTH (Kalshi)")
    bal = kget("/portfolio/balance")
    print(f"    cash: ${bal.get('balance_dollars')} | portfolio_value: {bal.get('portfolio_value')}")
    pos = kget("/portfolio/positions?limit=100")
    n = 0
    cost = 0.0
    for mp in pos.get("market_positions", []):
        fp = float(mp.get("position_fp") or 0)
        if fp == 0:
            continue
        n += 1
        c = float(mp.get("total_traded_dollars") or 0)
        cost += c
        print(f"    {mp['ticker'][:44]:44s} {fp:5.1f}ct cost=${c:.3f}")
    print(f"    {n} open positions, cost basis ${cost:.2f}")

    # ---- 4. UUID stream ----
    print("\n[5] UUID SIGNAL STREAM")
    try:
        import sqlite3
        scon = sqlite3.connect(ROOT / "data" / "uuid_stream.db")
        total = scon.execute("SELECT count(*) FROM stream").fetchone()[0]
        by_src = scon.execute("SELECT source, count(*) FROM stream GROUP BY source").fetchall()
        print(f"    {total} minted ticks: {dict(by_src)}")
        scon.close()
    except Exception as e:
        print(f"    stream read failed: {repr(e)[:60]}")
    print("\n" + "=" * 78)
    print("END REPORT — regenerated on demand, zero tokens. Logs: logs/run_*.jsonl")
    print("=" * 78)


if __name__ == "__main__":
    sys.exit(main())
