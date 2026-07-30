<!-- =============================================================================== file_id: SOM-DOC-0904-v1.0.0 name: DISASTER_RECOVERY.md description: DR recovery point for the GYST UUIDv8 prediction-market engine (local Postgres source of truth + Supabase subset + Vercel) project_id: PREDICTION-MARKET-ANALYSIS category: doc tags: [dr, backup, recovery, postgres, restore] created: 2026-07-30 modified: 2026-07-30 version: 1.0.0 agent_id: HERMES-AGENT =============================================================================== -->

# Disaster Recovery — UUID Engine

Recovery point created: **2026-07-30**. This document is the authoritative restore
procedure. All commands are Windows (no-admin, portable Postgres 16.4).

## 1. Captured state (this recovery point)
| component | value |
|---|---|
| Host | OMEN-01 (hostname), Win10 |
| Local Postgres | 16.4, portable, `D:\somacosf\outputs\prediction-market-analysis\.pg\pg16\pgsql` |
| Data dir | `...\.pg\data` |
| Cluster superuser | `postgres` (pw `hermes_pg_2026`, set in `.env_turso` locally — NOT in git) |
| `uuid_trades` rows | **42,236,500** (final, backfill complete) |
| `uuid_trades` size | 11 GB on disk |
| Markets (0x3A0) | Turso `uuid_vectors` (500 live rows) — separate system |
| Supabase project | `somacosf-uuid-engine`, ref `qxxuovjqdknxxzrnlpow`, org `SomacoSF` |
| Supabase subset | `uuid_trades_subset` (rolling 1.5M freshest rows, <500MB cap) |
| Vercel app | `app/` (Next.js), MAC/Tailscale passkey-gated, reads `PG_CONNECTION_STRING` |
| GitHub | `SoMaCoSF/prediction-market-analysis` (PRIVATE) |

## 2. Backup artifacts
| artifact | path | size |
|---|---|---|
| `uuid_trades` dump (custom -Fc) | `D:\somacosf\backups\manual\uuid_trades_DR_2026-07-30.dump` | 2.2 GB |
| Source scripts | git repo (committed) | — |
| Supabase subset | live in Supabase (re-derivable from local dump) | — |

> The dump is the ONLY irreplaceable artifact (42M rows). Supabase subset and Vercel
> are fully re-derivable from it. The dump lives OUTSIDE the git repo (never commit 2GB).

## 3. Restore procedure (local Postgres from dump)
```bat
REM 1) bring up a fresh portable Postgres (or reuse .pg/data)
cd D:\somacosf\outputs\prediction-market-analysis
.pg\pg16\pgsql\bin\pg_ctl.exe -D .pg\data -l .pg\logfile -o "-p 5432" start

REM 2) create the table + bitmask index (or let sync_supabase_subset.ensure_schema do it)
.pg\pg16\pgsql\bin\psql.exe -U postgres -h 127.0.0.1 -p 5432 -c "CREATE TABLE IF NOT EXISTS uuid_trades (uuid TEXT PRIMARY KEY, uuid_hi BIGINT NOT NULL, uuid_lo BIGINT NOT NULL, trade_id TEXT NOT NULL, market_id TEXT NOT NULL, price REAL NOT NULL, amount REAL NOT NULL, ts INTEGER NOT NULL, created_at TIMESTAMPTZ DEFAULT now());"
.pg\pg16\pgsql\bin\psql.exe -U postgres -h 127.0.0.1 -p 5432 -c "CREATE INDEX IF NOT EXISTS idx_uuid_trades_type ON uuid_trades (((uuid_hi >> 52) & 4095));"

REM 3) restore the dump
set PGPASSWORD=hermes_pg_2026
.pg\pg16\pgsql\bin\pg_restore.exe -U postgres -h 127.0.0.1 -p 5432 -d postgres -t uuid_trades -j 4 "D:\somacosf\backups\manual\uuid_trades_DR_2026-07-30.dump"

REM 4) verify
.pg\pg16\pgsql\bin\psql.exe -U postgres -h 127.0.0.1 -p 5432 -tAc "SELECT count(*) FROM uuid_trades;"
REM expect 42236500
```

## 4. Re-derive Supabase subset (after local restore)
```bash
# ensure .env_turso has SUPABASE_REF + SUPABASE_DB_PASSWORD (local only)
python scripts/sync_supabase_subset.py --subset-rows 1500000
```

## 5. Re-deploy Vercel (only with explicit GO)
```bash
cd app
vercel env add PG_CONNECTION_STRING   # Supabase subset URI
vercel env add STATUS_SALT           # passkey salt
vercel deploy --prod                 # GO required
```

## 6. Known gaps / honest notes
- Supabase live subset was 0 rows at DR time (COPY upload to free tier in progress/slow).
  Re-run step 4 after restore; it is fully re-derivable.
- MAC passkey is obfuscation (per user direction), not cryptographic auth.
- `ts` in snapshot is near-constant; "freshest" subset = deterministic row slice.
- Tailscale→Vercel full-local connect is Phase 2 (needs a relay host); not built yet.
- Vercel NOT deployed at DR time (awaiting explicit GO).

## 7. RPO / RTO
- RPO: bounded by last `sync_supabase_subset.py` run (subset) + last `pg_dump` (full).
  Schedule `pg_dump` + subset sync on a cron (e.g. nightly) to tighten RPO.
- RTO: ~10 min to restore 42M rows from 2.2GB dump on same host; +sync time for Supabase.
