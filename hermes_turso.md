Markdown
# TASK SPECIFICATION: Turso `uuid_vectors` Backfill Pipeline

## Objective
Build a high-throughput, idempotent Python backfill script (`scripts/turso_backfill.py`) that reads extracted prediction market Parquet files from `data/minted_parquet/`, mints canonical GYST UUIDv8 addresses, and inserts signal records into the Turso database table `uuid_vectors`.

---

## 1. Environment & Database Schema

### Turso Prerequisites
- Library: `@libsql/client` (or `libsql-experimental` in Python)
- Environment Variables required in `.env`:
  ```env
  TURSO_DATABASE_URL=libsql://your-database-name.turso.io
  TURSO_AUTH_TOKEN=your-turso-auth-token
Target Table Schema (uuid_vectors)
Ensure the table exists or is lazily created before backfilling:

SQL
CREATE TABLE IF NOT EXISTS uuid_vectors (
    uuid TEXT PRIMARY KEY,          -- Canonical GYST UUIDv8 string (Type 0x3A0)
    market_id TEXT NOT NULL,         -- Source ticker / market key
    venue_id INTEGER NOT NULL,       -- 200 = Polymarket, 201 = Kalshi
    signal REAL NOT NULL,            -- Quantized forecast / confidence signal [0.0 - 1.0]
    provenance INTEGER NOT NULL,     -- Prov code (e.g., 0x07 for POLY_MAKER, 0x01 for DEXTER)
    timestamp INTEGER NOT NULL,      -- Unix timestamp in seconds
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_uuid_vectors_market ON uuid_vectors(market_id);
2. Requirements & Execution Logic
Key Requirements
Source Data Directory: Read all *.parquet files from data/minted_parquet/.

GYST UUID Generation: Import encode_poly_market_uuid from uuid_service_turboquant.py to deterministically derive UUIDs from the market ticker / trade record.

Idempotency & Batching:

Use INSERT INTO uuid_vectors (...) VALUES (...) ON CONFLICT(uuid) DO NOTHING.

Execute batch inserts in chunks of 500 rows per SQL transaction to maximize Turso throughput.

Progress Reporting:

Log rate (rows/sec) and progress every 10,000 processed records.

CLI Parameters:

--batch-size N: Batch insert size (default: 500).

--dry-run: Print sample records and count without writing to Turso.

--limit N: Limit max total rows processed (useful for testing).

3. Reference Implementation Outline
Python
#!/usr/bin/env python3
"""
scripts/turso_backfill.py
Reads data/minted_parquet/*.parquet, mints GYST UUIDv8 IDs, 
and batch-inserts into Turso `uuid_vectors`.
"""

import os
import sys
import glob
import time
import argparse
from pathlib import Path
import duckdb
import libsql_experimental as libsql

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from uuid_service_turboquant import (
    encode_poly_market_uuid,
    PROV_POLY_MAKER
)

def get_turso_client():
    url = os.getenv("TURSO_DATABASE_URL")
    token = os.getenv("TURSO_AUTH_TOKEN")
    if not url or not token:
        raise ValueError("Missing TURSO_DATABASE_URL or TURSO_AUTH_TOKEN in environment.")
    return libsql.connect(database=url, auth_token=token)

def init_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS uuid_vectors (
            uuid TEXT PRIMARY KEY,
            market_id TEXT NOT NULL,
            venue_id INTEGER NOT NULL,
            signal REAL NOT NULL,
            provenance INTEGER NOT NULL,
            timestamp INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

def run_backfill(batch_size=500, limit=float("inf"), dry_run=False):
    parquet_files = glob.glob(str(PROJECT_ROOT / "data" / "minted_parquet" / "*.parquet"))
    print(f"[*] Found {len(parquet_files)} parquet files to process.")

    conn = None if dry_run else get_turso_client()
    if conn:
        init_schema(conn)

    # Use DuckDB to efficiently query local parquet files
    con = duckdb.connect(":memory:")
    
    total_processed = 0
    batch = []

    for p_file in parquet_files:
        df = con.execute(f"SELECT * FROM '{p_file}'").fetchdf()
        
        for _, row in df.iterrows():
            market_id = str(row.get("ticker", row.get("market_id", Path(p_file).stem)))
            timestamp = int(row.get("timestamp", time.time()))
            
            # Mint 128-bit GYST UUIDv8
            uuid_str = encode_poly_market_uuid(
                market_id=market_id,
                confidence=1.0,
                timestamp_sec=timestamp
            )

            record = (uuid_str, market_id, 200, 1.0, PROV_POLY_MAKER, timestamp)
            batch.append(record)
            total_processed += 1

            if len(batch) >= batch_size:
                if not dry_run and conn:
                    # Execute batch insert ON CONFLICT IGNORE
                    placeholders = ",".join(["(?, ?, ?, ?, ?, ?)"] * len(batch))
                    query = f"INSERT INTO uuid_vectors (uuid, market_id, venue_id, signal, provenance, timestamp) VALUES {placeholders} ON CONFLICT(uuid) DO NOTHING"
                    flat_args = [item for sublist in batch for item in sublist]
                    conn.execute(query, flat_args)
                batch.clear()

            if total_processed >= limit:
                break
        if total_processed >= limit:
            break

    # Flush remaining
    if batch and not dry_run and conn:
        placeholders = ",".join(["(?, ?, ?, ?, ?, ?)"] * len(batch))
        query = f"INSERT INTO uuid_vectors (uuid, market_id, venue_id, signal, provenance, timestamp) VALUES {placeholders} ON CONFLICT(uuid) DO NOTHING"
        flat_args = [item for sublist in batch for item in sublist]
        conn.execute(query, flat_args)

    print(f"[*] Completed Turso backfill. Processed {total_processed} records.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--limit", type=int, default=1000000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run_backfill(batch_size=args.batch_size, limit=args.limit, dry_run=args.dry_run)