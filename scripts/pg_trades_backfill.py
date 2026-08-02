#!/usr/bin/env python3
"""
scripts/pg_trades_backfill.py

Postgres-targeted backfill for GYST UUIDv8 trade records (type 0x3A2).

Why Postgres (not Turso/SQLite):
  SQLite integers are 64-bit, so a 128-bit GYST UUID can NEVER be bitmasked in
  SQL (the doc's `(CAST(uuid AS INT) >> 116)` silently returns 0). Postgres
  stores the UUID as two BIGINT columns (uuid_hi, uuid_lo) and supports native
  `>>` / `&` operators, so the wirespeed routing check
      ((uuid_hi >> 52) & 4095) = 0x3A2
  is a real, indexable SQL operation.

Markets-first preserved: this writes ONLY the `uuid_trades` table. The existing
Turso `uuid_vectors` (markets, 0x3A0) is never touched.

Schema:
  uuid_trades(
    uuid TEXT PRIMARY KEY,
    uuid_hi BIGINT NOT NULL,   -- high 64 bits of the 128-bit UUID
    uuid_lo BIGINT NOT NULL,   -- low  64 bits
    trade_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    price REAL NOT NULL,        -- executed price proxy [0,1] packed into signal
    amount REAL NOT NULL,
    ts INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
  )
  + partial index on type for wirespeed routing:
    CREATE INDEX ... ON uuid_trades (( (uuid_hi >> 52) & 4095 )) WHERE ((uuid_hi>>52)&4095)=0x3A2;
"""
from __future__ import annotations

import os
import sys
import glob
import time
import json
import argparse
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import duckdb
import psycopg2  # pip install psycopg2-binary

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from uuid_service_turboquant import encode_poly_trade_uuid  # noqa: E402

DEFAULT_BATCH_SIZE = 500
REPORT_EVERY = 10_000

_MARKET_TOKEN_MAP: Dict[str, Tuple[str, str]] = {}

TYPE_TRADE = 0x3A2

CREATE_TABLE_STMT = """
CREATE TABLE IF NOT EXISTS uuid_trades (
    uuid      TEXT PRIMARY KEY,
    uuid_hi   BIGINT NOT NULL,
    uuid_lo   BIGINT NOT NULL,
    trade_id  TEXT NOT NULL,
    market_id TEXT NOT NULL,
    price     REAL NOT NULL,
    amount    REAL NOT NULL,
    ts        INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
"""
CREATE_INDEX_STMT = """
CREATE INDEX IF NOT EXISTS idx_uuid_trades_type
    ON uuid_trades (((uuid_hi >> 52) & 4095));
CREATE INDEX IF NOT EXISTS idx_uuid_trades_market
    ON uuid_trades (market_id);
"""


def _uuid_to_hilo(uuid_str: str) -> Tuple[int, int]:
    """Split a 32-hex-char UUID (dashes optional) into two unsigned 64-bit ints."""
    h = uuid_str.replace("-", "")
    hi = int(h[:16], 16)
    lo = int(h[16:], 16)
    # store as signed BIGINT (Postgres int8); convert to signed range
    if hi >= 2**63:
        hi -= 2**64
    if lo >= 2**63:
        lo -= 2**64
    return hi, lo


def _load_market_token_map() -> Dict[str, Tuple[str, str]]:
    if _MARKET_TOKEN_MAP:
        return _MARKET_TOKEN_MAP
    market_files = sorted(glob.glob(str(PROJECT_ROOT / "data" / "minted_parquet" / "markets_*.parquet")))
    con = duckdb.connect(":memory:")
    for mf in market_files:
        try:
            rows = con.execute(
                f"SELECT id, gyst_uuid, unnest(json_transform(clob_token_ids,'[\"VARCHAR\"]')) AS token "
                f"FROM read_parquet('{mf}')"
            ).fetchall()
        except Exception as exc:
            print(f"[warn] market token map skip {Path(mf).name}: {exc}")
            continue
        for market_id, market_uuid, token in rows:
            if token:
                _MARKET_TOKEN_MAP[str(token)] = (str(market_id), str(market_uuid))
    print(f"[*] Market token map: {len(_MARKET_TOKEN_MAP):,} token ids -> markets")
    return _MARKET_TOKEN_MAP


def _connect() -> psycopg2.extensions.connection:
    dsn = os.getenv("PG_DSN") or os.getenv("POSTGRES_DSN") or None
    if dsn:
        return psycopg2.connect(dsn)
    return psycopg2.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "postgres"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "hermes_pg_2026"),
    )


def _read_trades(path: Path) -> Iterable[dict]:
    con = duckdb.connect(":memory:")
    rel = con.from_parquet(str(path))
    cols = [c for c in ("transaction_hash", "maker_asset_id", "taker_asset_id",
                        "maker_amount", "taker_amount", "timestamp") if c in rel.columns]
    df = rel.project(", ".join([f'"{c}"' for c in cols])).to_df()
    yield from df.to_dict(orient="records")


def _coerce(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _compose_trade_row(rec: dict, token_map: Dict[str, Tuple[str, str]], fallback_market: str):
    tx = rec.get("transaction_hash") or rec.get("order_hash") or ""
    maker_a = rec.get("maker_asset_id")
    taker_a = rec.get("taker_asset_id")
    asset = str(taker_a) if str(maker_a) in ("0", "", "None") else str(maker_a)
    market_id, market_uuid = token_map.get(asset, (fallback_market, ""))
    maker_amt = _coerce(rec.get("maker_amount"))
    taker_amt = _coerce(rec.get("taker_amount"))
    total = maker_amt + taker_amt
    price = (taker_amt / total) if total > 0 else 0.0
    amount = max(maker_amt, taker_amt)
    ts = int(rec.get("timestamp") or time.time())
    uuid_str = encode_poly_trade_uuid(
        trade_id=tx, price=price, timestamp_sec=ts, market_uuid=market_uuid or None
    )
    hi, lo = _uuid_to_hilo(uuid_str)
    return (uuid_str, hi, lo, tx, market_id, price, amount, ts)


def run_backfill(batch_size: int = DEFAULT_BATCH_SIZE, limit: int = 10 ** 9, dry_run: bool = False) -> None:
    trade_files = sorted(glob.glob(str(PROJECT_ROOT / "data" / "minted_parquet" / "trades_*.parquet")))
    print(f"[*] Found {len(trade_files):,} trades files to process.")

    token_map = {} if dry_run else _load_market_token_map()
    conn = None if dry_run else _connect()
    if conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_STMT)
            cur.execute(CREATE_INDEX_STMT)
            conn.commit()
        print("[*] Schema ready (uuid_trades + indexes).")

    total = 0
    rows: List[Tuple] = []
    last_report = 0
    t0 = time.perf_counter()

    for tf in trade_files:
        try:
            recs = list(_read_trades(Path(tf)))
        except Exception as exc:
            print(f"[skip] {Path(tf).name}: {exc}")
            continue
        for rec in recs:
            rows.append(_compose_trade_row(rec, token_map, Path(tf).stem))
            total += 1
            if len(rows) >= batch_size:
                if conn:
                    _exec_batch(conn, rows)
                rows.clear()
            if total - last_report >= REPORT_EVERY or total >= limit:
                el = time.perf_counter() - t0
                rate = (total / el) if el > 0 else 0.0
                print(f"[progress] processed={total:,} rate={rate:,.0f}/sec{'(dry)' if dry_run else ''}")
                last_report = total
            if total >= limit:
                break
        if total >= limit:
            break

    if rows:
        if conn:
            _exec_batch(conn, rows)
        rows.clear()
    if conn:
        conn.close()

    el = time.perf_counter() - t0
    rate = (total / el) if el > 0 else 0.0
    print(f"[*] Completed trades backfill: {total:,} records{', ' + format(rate, ',.0f') + ' rows/sec' if rate else ''}{' (dry-run)' if dry_run else ''}.")


def _exec_batch(conn, rows: List[Tuple]) -> None:
    sql = (
        "INSERT INTO uuid_trades (uuid, uuid_hi, uuid_lo, trade_id, market_id, price, amount, ts) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (uuid) DO NOTHING"
    )
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Backfill uuid_trades (0x3A2) into Postgres + pgvector.")
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    ap.add_argument("--limit", type=int, default=10 ** 9)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run_backfill(batch_size=args.batch_size, limit=args.limit, dry_run=args.dry_run)
