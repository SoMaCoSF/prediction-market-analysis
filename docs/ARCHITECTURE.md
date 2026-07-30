<!-- =============================================================================== file_id: SOM-DOC-0903-v1.0.0 name: ARCHITECTURE.md description: Full architecture of the GYST UUIDv8 prediction-market engine (local Postgres + Supabase subset + Vercel) project_id: PREDICTION-MARKET-ANALYSIS category: doc tags: [architecture, gyst, uuid, postgres, supabase, vercel] created: 2026-07-30 modified: 2026-07-30 version: 1.0.0 agent_id: HERMES-AGENT =============================================================================== -->

# Architecture — GYST UUIDv8 Prediction-Market Engine

## Thesis
Convert the 30 GB Polymarket corpus into **GYST UUIDv8** addresses so the UUID itself is the
**wirespeed maths key**: type, namespace, timestamp, provenance, and a 16-bit signal are packed
into 128 bits and recoverable by O(1) bitmask — no DB lookup, no string parse. The UUID is the
single channel with deep depth on content + context.

## Layered topology
```
┌─ LOCAL (OMEN-01, no-admin portable Postgres 16.4) ── source of truth, full ~38M rows
│     uuid_trades (0x3A2 trades) · uuid_hi/uuid_lo BIGINT · bitmask index
│     MAC/Tailscale gated · viewer on :4242
└─ GH repo (private SoMaCoSF/prediction-market-analysis) ── deploy source
        │
        ├─ SUPABASE (free 500 MB) ── rolling FRESHEST subset (~1.5M rows) < 500 MB
        │     uuid_trades_subset · same schema + bitmask index
        │
        └─ VERCEL ── status site, passkey = SHA-256(OMEN-01 MAC | hostname | salt)
                  reads Supabase via PG_CONNECTION_STRING (live) + build-time snapshot
```

## Why Postgres, not Turso/SQLite
SQLite/Turso integers are 64-bit. A 128-bit UUID **cannot** be bitmasked in SQL: the doc's
`(CAST(uuid AS INT) >> 116) & 0xFFF` returns **0** (proven against live Turso). Postgres stores
the UUID as two `BIGINT` (`uuid_hi`, `uuid_lo`); `(uuid_hi >> 52) & 4095 = 0x3A2` is a **native,
indexable** operation. This is the actual wirespeed routing — impossible on Turso.

## Data flow
1. **Extract**: `data/data.tar.zst` → `data/minted_parquet/` (markets_*.parquet + trades_*.parquet).
2. **Join**: each trade's `maker_asset_id`/`taker_asset_id` resolves to its parent market via the
   market's `clob_token_ids` (2-token array). Verified: 5/5 sample trades → real markets;
   token map = 817,683 entries.
3. **Mint**: `encode_poly_trade_uuid` (0x3A2) packs price into the 16-bit signal slot; namespace
   derived from parent `market_uuid` so trades group under their market's address space.
4. **Store**: `pg_trades_backfill_parallel.py` — 11 encoder procs + 4 writer procs → local
   `uuid_trades` (~20,550 rows/sec, 4.6× serial). Markets (0x3A0) live in Turso `uuid_vectors`.
5. **Subset**: `sync_supabase_subset.py` → latest 1.5M rows to Supabase `uuid_trades_subset`
   (rolling fresh slice, stays under 500 MB; ~291 B/row → ~440 MB).
6. **Serve**: Vercel status site (MAC/Tailscale passkey-gated) reads Supabase live.

## Verification
- `proof_transaction.py`: per-transaction round-trip on 3,000 real rows — **0 failures**, 100%
  bitmask routing, types distinguishable. (`ALL TRANSACTIONS VERIFIED`.)
- `wirespeed` query on full table: `((uuid_hi >> 52) & 4095) = 0x3A2` matches 100% of trade rows.
- In-memory bitmask benchmark: ~1.49 Mops/sec (pure Python int shift/mask, no DB).

## Honest caveats
- `ts` field in the snapshot has near-zero variance → "freshest" subset = latest by (ts,uuid),
  effectively a deterministic row slice, not a true time window.
- MAC passkey is obfuscation (per user direction), adequate for a status page on this box/Tailscale.
- pgvector intentionally deferred (no embedding layer yet); bitmask needs only core Postgres.
- Supabase sync throughput on free tier is slow (~minutes for 1.5M rows); resumable (no truncate).

## Key files
| path | role |
|---|---|
| `scripts/uuid_service_turboquant.py` | GYST encode/decode + 0x3A0/0x3A1/0x3A2 encoders |
| `scripts/pg_trades_backfill_parallel.py` | parallel local backfill (11e/4w) |
| `scripts/sync_supabase_subset.py` | rolling subset → Supabase |
| `scripts/server_view.py` | localhost:4242 viewer (live PG + Turso + decoder) |
| `scripts/proof_transaction.py` | per-transaction verification harness |
| `scripts/start_pg.bat` | no-admin Postgres + viewer startup |
| `app/` | Next.js Vercel status site (passkey-gated) |
| `docs/GHOST_CATALOG.md` | Ghost Catalog header spec (all artifacts) |
