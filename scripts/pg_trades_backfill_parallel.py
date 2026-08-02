#!/usr/bin/env python3
"""
scripts/pg_trades_backfill_parallel.py

Parallel backfill of GYST UUIDv8 trade records (type 0x3A2) into local Postgres.

Architecture (Windows-safe, spawn-based multiprocessing):
  - N_ENCODERS reader/encoder processes. Each loads the shared market->token map
    once (in its initializer), then pulls trade files, reads with DuckDB, joins to
    the parent market via clob_token_ids, mints 0x3A2 UUIDs, and pushes row
    batches onto a multiprocessing.Queue.
  - N_WRITERS processes, each owning its own psycopg2 connection, pop batches off
    the queue and executemany into uuid_trades (ON CONFLICT DO NOTHING => safe
    resume over an interrupted run).
  - Sentinels (one per encoder) tell writers when input is exhausted.

The encode step is the expensive part (DuckDB read + Python UUID pack + FNV hash)
and is fully parallel. PG writes stay batched and connection-pooled.

Markets-first preserved: writes ONLY uuid_trades. Turso uuid_vectors untouched.
"""
from __future__ import annotations

import os
import sys
import glob
import time
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb
import psycopg2
from multiprocessing import Process, Queue, cpu_count

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from uuid_service_turboquant import encode_poly_trade_uuid  # noqa: E402

DEFAULT_ENCODERS = 12
DEFAULT_WRITERS = 4
BATCH_PER_WORKER = 1000
REPORT_EVERY = 500_000

# populated per-worker in _init_encoder
_TOKEN_MAP: Dict[str, Tuple[str, str]] = {}


def _uuid_to_hilo(uuid_str: str) -> Tuple[int, int]:
    h = uuid_str.replace("-", "")
    hi = int(h[:16], 16)
    lo = int(h[16:], 16)
    if hi >= 2**63:
        hi -= 2**64
    if lo >= 2**63:
        lo -= 2**64
    return hi, lo


def _build_token_map() -> Dict[str, Tuple[str, str]]:
    m: Dict[str, Tuple[str, str]] = {}
    market_files = sorted(glob.glob(str(PROJECT_ROOT / "data" / "minted_parquet" / "markets_*.parquet")))
    con = duckdb.connect(":memory:")
    for mf in market_files:
        try:
            for market_id, market_uuid, token in con.execute(
                f"SELECT id, gyst_uuid, unnest(json_transform(clob_token_ids,'[\"VARCHAR\"]')) "
                f"FROM read_parquet('{mf}')"
            ).fetchall():
                if token:
                    m[str(token)] = (str(market_id), str(market_uuid))
        except Exception as exc:
            print(f"[warn] token map skip {Path(mf).name}: {exc}", flush=True)
    return m


def _init_encoder():
    global _TOKEN_MAP
    if not _TOKEN_MAP:
        _TOKEN_MAP = _build_token_map()
        print(f"[encoder-init] token map ready: {len(_TOKEN_MAP):,} entries", flush=True)


def _coerce(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def _encode_file(tf: str) -> List[Tuple]:
    rows: List[Tuple] = []
    try:
        con = duckdb.connect(":memory:")
        rel = con.from_parquet(tf)
        cols = [c for c in ("transaction_hash", "maker_asset_id", "taker_asset_id",
                            "maker_amount", "taker_amount", "timestamp") if c in rel.columns]
        if not cols:
            return rows
        df = rel.project(", ".join([f'"{c}"' for c in cols])).to_df()
        for rec in df.to_dict(orient="records"):
            tx = rec.get("transaction_hash") or rec.get("order_hash") or ""
            maker_a = rec.get("maker_asset_id")
            taker_a = rec.get("taker_asset_id")
            asset = str(taker_a) if str(maker_a) in ("0", "", "None") else str(maker_a)
            market_id, market_uuid = _TOKEN_MAP.get(asset, (Path(tf).stem, ""))
            maker_amt = _coerce(rec.get("maker_amount"))
            taker_amt = _coerce(rec.get("taker_amount"))
            total = maker_amt + taker_amt
            price = (taker_amt / total) if total > 0 else 0.0
            amount = max(maker_amt, taker_amt)
            ts = int(rec.get("timestamp") or time.time())
            uuid_str = encode_poly_trade_uuid(tx, price, timestamp_sec=ts, market_uuid=market_uuid or None)
            hi, lo = _uuid_to_hilo(uuid_str)
            rows.append((uuid_str, hi, lo, tx, market_id, price, amount, ts))
    except Exception as exc:
        print(f"[skip] {Path(tf).name}: {exc}", flush=True)
    return rows


def encoder_loop(file_q: Queue, row_q: Queue, sentinel: object):
    _init_encoder()
    while True:
        item = file_q.get()
        if item is sentinel:
            break
        rows = _encode_file(item)
        # push in sub-batches to keep memory bounded
        for i in range(0, len(rows), BATCH_PER_WORKER):
            row_q.put(rows[i:i + BATCH_PER_WORKER])
    row_q.put(sentinel)


def writer_loop(row_q: Queue, sentinel: object, n_encoders: int):
    conn = psycopg2.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "postgres"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "hermes_pg_2026"),
        connect_timeout=10,
    )
    sql = (
        "INSERT INTO uuid_trades (uuid, uuid_hi, uuid_lo, trade_id, market_id, price, amount, ts) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (uuid) DO NOTHING"
    )
    done_encoders = 0
    while True:
        item = row_q.get()
        if item is sentinel:
            done_encoders += 1
            if done_encoders >= n_encoders:
                break
            continue
        with conn.cursor() as cur:
            cur.executemany(sql, item)
        conn.commit()
    conn.close()


def run(encoders: int = DEFAULT_ENCODERS, writers: int = DEFAULT_WRITERS, limit: int = 10**9):
    trade_files = sorted(glob.glob(str(PROJECT_ROOT / "data" / "minted_parquet" / "trades_*.parquet")))
    if limit < len(trade_files):
        trade_files = trade_files[:limit]
    print(f"[*] {len(trade_files):,} trade files · {encoders} encoders · {writers} writers", flush=True)

    # ensure schema exists (idempotent)
    boot = psycopg2.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "postgres"), user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "hermes_pg_2026"), connect_timeout=10,
    )
    with boot.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS uuid_trades (
                uuid TEXT PRIMARY KEY, uuid_hi BIGINT NOT NULL, uuid_lo BIGINT NOT NULL,
                trade_id TEXT NOT NULL, market_id TEXT NOT NULL, price REAL NOT NULL,
                amount REAL NOT NULL, ts INTEGER NOT NULL, created_at TIMESTAMPTZ DEFAULT now());
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_uuid_trades_type ON uuid_trades (((uuid_hi >> 52) & 4095));")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_uuid_trades_market ON uuid_trades (market_id);")
    boot.commit()
    boot.close()

    sentinel = object()
    file_q: Queue = Queue(maxsize=encoders * 4)
    row_q: Queue = Queue(maxsize=writers * 8)

    procs: List[Process] = []
    for _ in range(writers):
        p = Process(target=writer_loop, args=(row_q, sentinel, encoders), daemon=True)
        p.start(); procs.append(p)
    for _ in range(encoders):
        p = Process(target=encoder_loop, args=(file_q, row_q, sentinel), daemon=True)
        p.start(); procs.append(p)

    total = 0
    t0 = time.perf_counter()
    last_report = 0
    # feed files; block when queue full
    for tf in trade_files:
        file_q.put(tf)
        total += 1
        if total - last_report >= REPORT_EVERY:
            el = time.perf_counter() - t0
            rate = total / el if el > 0 else 0
            print(f"[feed] queued {total:,} files · est {rate:,.0f}/sec", flush=True)
            last_report = total
    # signal encoders done
    for _ in range(encoders):
        file_q.put(sentinel)
    for p in procs:
        p.join()

    el = time.perf_counter() - t0
    rate = (total / el) if el > 0 else 0
    print(f"[*] All files dispatched: {total:,} · wall {el:,.0f}s · ~{rate:,.0f} files/sec", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--encoders", type=int, default=DEFAULT_ENCODERS)
    ap.add_argument("--writers", type=int, default=DEFAULT_WRITERS)
    ap.add_argument("--limit", type=int, default=10**9, help="limit number of trade files (debug)")
    args = ap.parse_args()
    n = cpu_count() or 8
    enc = min(args.encoders, n - args.writers - 1) if (args.encoders + args.writers) >= n else args.encoders
    run(encoders=max(1, enc), writers=args.writers, limit=args.limit)
