#!/usr/bin/env python3
"""
scripts/sync_supabase_subset.py

Sync a ROLLING FRESH SUBSET of the local uuid_trades table to Supabase (free 500MB).

Why a subset: local Postgres holds the full ~38M-row dataset (the source of truth,
MAC-gated, infinite capacity). Supabase free tier is 500MB ~= 1.7M rows at ~291 B/row.
So we push only the most recent SUBSET_ROWS (by ts DESC, uuid) into Supabase; Vercel
reads that for live status. Re-run on a schedule (cron) to keep it fresh.

Strategy note: the parquet `ts` field has almost no variance across the snapshot, so we
slice by ROW COUNT (latest N by (ts DESC, uuid)), NOT by a time window.

Target table in Supabase must already exist (same schema as local uuid_trades). Create it
once with scripts/supabase_schema.sql (or let this script create it idempotently).

Env:
  PGCONNECTIONSTRING (Supabase postgres:// URI)  -- required
  SUBSET_ROWS (default 1_500_000)
  Local PG: PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD (default 127.0.0.1:5432/postgres)
"""
from __future__ import annotations

import os
import sys
import time
import argparse
from pathlib import Path

import psycopg2
from psycopg2 import sql

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

DEFAULT_SUBSET = 1_500_000
BATCH = 5000


def local_conn():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "postgres"), user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "hermes_pg_2026"), connect_timeout=10,
    )


def supabase_conn():
    cs = os.getenv("PGCONNECTIONSTRING") or os.getenv("PG_CONNECTION_STRING")
    if not cs:
        raise SystemExit("Missing PGCONNECTIONSTRING (Supabase URI).")
    return psycopg2.connect(cs, connect_timeout=15)


def ensure_schema(con):
    with con.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS uuid_trades_subset (
                uuid TEXT PRIMARY KEY, uuid_hi BIGINT NOT NULL, uuid_lo BIGINT NOT NULL,
                trade_id TEXT NOT NULL, market_id TEXT NOT NULL, price REAL NOT NULL,
                amount REAL NOT NULL, ts INTEGER NOT NULL, created_at TIMESTAMPTZ DEFAULT now());
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sub_type ON uuid_trades_subset (((uuid_hi >> 52) & 4095));")
    con.commit()


def run(subset_rows: int):
    t0 = time.perf_counter()
    lc = local_conn()
    sc = supabase_conn()
    ensure_schema(sc)

    # pull latest N rows from local
    with lc.cursor() as cur:
        cur.execute(
            "SELECT uuid, uuid_hi, uuid_lo, trade_id, market_id, price, amount, ts "
            f"FROM uuid_trades ORDER BY ts DESC, uuid DESC LIMIT {int(subset_rows)}"
        )
        rows = cur.fetchall()
    lc.close()
    print(f"[*] pulled {len(rows):,} rows from local (subset={subset_rows:,})", flush=True)

    # bulk load via COPY (10-50x faster than executemany on Supabase free tier)
    import io
    buf = io.StringIO()
    for r in rows:
        # tab-separated, no header; NULL-safe
        buf.write("\t".join(str(x) for x in r) + "\n")
    buf.seek(0)
    with sc.cursor() as cur:
        cur.copy_expert(
            "COPY uuid_trades_subset (uuid, uuid_hi, uuid_lo, trade_id, market_id, price, amount, ts) "
            "FROM STDIN WITH (FORMAT text, NULL '')",
            buf,
        )
        sc.commit()
    sc.close()

    el = time.perf_counter() - t0
    print(f"[*] synced {len(rows):,} rows to Supabase in {el:,.1f}s", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset-rows", type=int, default=DEFAULT_SUBSET)
    args = ap.parse_args()
    run(args.subset_rows)
