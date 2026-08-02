-- scripts/supabase_schema.sql
-- Run this ONCE in Supabase (SQL editor) to create the rolling-subset table.
-- Keeps a fresh slice of the local uuid_trades under the 500MB free-tier ceiling.

CREATE TABLE IF NOT EXISTS uuid_trades_subset (
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

-- wirespeed bitmask routing index (same as local)
CREATE INDEX IF NOT EXISTS idx_sub_type
    ON uuid_trades_subset (((uuid_hi >> 52) & 4095));
CREATE INDEX IF NOT EXISTS idx_sub_market
    ON uuid_trades_subset (market_id);

-- NOTE: sync_supabase_subset.py truncates + re-inserts a rolling window of the
-- latest SUBSET_ROWS rows from the local full table. Vercel reads this table via
-- PG_CONNECTION_STRING for live status.
