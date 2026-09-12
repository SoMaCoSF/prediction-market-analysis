# MINTED PARQUET CORPUS — `data/minted_parquet` (survey 2026-09-12)

> Static survey: every file's parquet footer read via pyarrow metadata (all 38,152 files, 45 s). Nothing modified, nothing executed against the data. Raw per-file audit: `%TEMP%\pma_minted_markets.jsonl`, `%TEMP%\pma_minted_trades.jsonl`.

## What it is

Polymarket export corpus, mint-ready: **markets** (already UUID-minted — every row carries `gyst_uuid`, 0x3A0 lineage) + **on-chain trades** (raw fuel for the 0x3A2 mint into `uuid_trades`). Per the backfill-ops doctrine, this folder is the **true DR source** for the UUID-native store.

## Totals

| Family | Files | Rows | Size | Coverage | Minted |
|---|---|---|---|---|---|
| `markets_*.parquet` | 41 | 408,863 | 66.2 MB | 0 .. 408,863 — **complete, 0 gaps, 0 dups** (final file partial: 400000–408863, expected) | 2026-07-30 11:38 |
| `trades_*.parquet` | 38,111 | **381,107,336** | **26.09 GB** | 0 .. 404,540,000; **1,936 gaps = 23,430,000 rows (~2.3%)**; 0 dups; 0 partial files | 2026-07-30 11:38–12:05 |
| **Total** | **38,152** | **381,516,199** | ~26.15 GB | | |

## Schemas (consistent across every sampled file — 0 mismatches)

- **markets:** `id, condition_id, question, slug, outcomes, outcome_prices, clob_token_ids, volume, liquidity, active, closed, end_date, created_at, market_maker_address, _fetched_at, gyst_uuid`
- **trades:** `block_number, transaction_hash, log_index, order_hash, maker, taker, maker_asset_id, taker_asset_id, maker_amount, taker_amount, fee, timestamp, _fetched_at, _contract`

Content samples: markets span the full Polymarket era — first shard is `will-joe-biden-get-coronavirus-before-the-election` (created 2020-10-02) → mid shard `elc-der-wre-2026-01-04-total-4pt5` (created 2025-12-30). Trades span both exchange contracts: `CTF Exchange` + `NegRisk CTF Exchange`.

## Trades coverage gaps (the only incompleteness)

- 1,936 missing windows of 10k rows = 23.43M rows (~2.3% of the span).
- First gaps: `2.31M, 2.36M, 2.42M, 2.45M, 2.54M, 3.21M, 3.26M, 3.30M …` — last: `… 403.88M, 403.91M, 404.00M, 404.37M, 404.41M`.
- Biggest gap: `10,960,000–10,980,000` (2 windows). Everything else is single windows — looks like scattered fetch misses, not structural holes.
- Re-fetchable if an airtight corpus is ever needed.

## Notes for downstream use

- Trades have **no `market_id`** by design → join trades→markets via `clob_token_ids` (recipe: fleet skill `turso-parquet-backfill` → `references/trades_backfill_pattern.md`; 817,683 token→market entries verified previously).
- `timestamp` is NULL in sourced trade rows; `_fetched_at` = fetch date (2026-01-29/30 for the rows seen); file mtimes = mint/convert date (2026-07-30) — four+ months old as of this survey.
- Fleet tie-in: this is the Polymarket-side data engine behind the fleet's Poly signal lanes (`shadow_index`, `whale_copier`) and the Turso/Supabase UUID pipeline.
- **Consumers** (scripts referencing `minted_parquet`): `pg_trades_backfill.py` + `pg_trades_backfill_parallel.py`, `stream_mint_backfill.py`, `turso_backfill.py`, `turso_trades_backfill.py`, `server_view.py` (local viewer), `_probe_trades.py`.
- Tooling env: `.venv311` = Python 3.11.14 + pyarrow 25.0.0 (the env this survey ran on).
