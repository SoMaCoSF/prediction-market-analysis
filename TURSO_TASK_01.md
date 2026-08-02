Markdown
# TASK SPECIFICATION: Turso `uuid_vectors` Backfill Pipeline

## Objective
Build a high-throughput, idempotent Python backfill script (`scripts/turso_backfill.py`) that reads extracted prediction market Parquet files from `data/minted_parquet/`, mints canonical GYST UUIDv8 addresses, and inserts signal records into the Turso database table `uuid_vectors`.

---

## 1. Environment & Database Schema

### Target Table Schema (`uuid_vectors`)
Ensure the table exists or is lazily created before backfilling:

```sql
CREATE TABLE IF NOT EXISTS uuid_vectors (
    uuid TEXT PRIMARY KEY,          -- Canonical GYST UUIDv8 string (Type 0x3A0)
    market_id TEXT NOT NULL,         -- Source ticker / market key
    venue_id INTEGER NOT NULL,       -- 200 = Polymarket, 201 = Kalshi
    signal REAL NOT NULL,            -- Quantized forecast / confidence signal [0.0 - 1.0]
    provenance INTEGER NOT NULL,     -- Prov code (e.g., 0x07 for POLY_MAKER)
    timestamp INTEGER NOT NULL,      -- Unix timestamp in seconds
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_uuid_vectors_market ON uuid_vectors(market_id);
2. Requirements & Execution Logic
Source Data: Read all *.parquet files in data/minted_parquet/.

UUID Encoding: Import encode_poly_market_uuid from uuid_service_turboquant.py.

Idempotent Batch Insert:

Use INSERT INTO uuid_vectors (...) VALUES (...) ON CONFLICT(uuid) DO NOTHING.

Batch in chunks of 500 rows per SQL transaction.

CLI Parameters:

--batch-size N (default: 500)

--dry-run (verify pipeline without modifying Turso)

--limit N (cap row processing for fast verification)


#### Step 2: Test the Turso Ingest Script
Once Hermes creates `scripts/turso_backfill.py`, run a dry run over the newly extracted Parquet files:

```bash
uv run scripts/turso_backfill.py --dry-run --limit 1000
When verified, execute the live backfill:

Bash
uv run scripts/turso_backfill.py --batch-size 500