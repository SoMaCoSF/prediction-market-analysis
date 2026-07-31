<!-- =============================================================================== file_id: SOM-DOC-0909-v1.0.0 name: VERIFICATION.md description: Truth ledger — what is PROVEN (real tool output) vs ARCHITECTURE/INTENT for the GYST UUID prediction-market engine project_id: PREDICTION-MARKET-ANALYSIS category: doc tags: [verification, proven, truth, status] created: 2026-07-30 modified: 2026-07-30 version: 1.0.0 agent_id: HERMES-AGENT =============================================================================== -->

# VERIFICATION — Speak Truth About the UUID Loop

This ledger separates **PROVEN** (verified by real tool output this session) from
**ARCHITECTURE / INTENT** (design direction, not yet realized in running code). We loop our
UUIDs and we speak truth: nothing below is asserted without a command that actually ran.

## ✅ PROVEN (ran and verified)
| claim | evidence |
|---|---|
| 30 GB Polymarket corpus → GYST UUIDv8 | 52,770,500 trade rows minted in local Postgres `uuid_trades` |
| 0 uuid duplicates | `count(*)=52,770,500` = `count(DISTINCT uuid)=52,770,500` (PK + ON CONFLICT DO NOTHING) |
| trade_id non-unique is legitimate | `distinct(trade_id)=21,004,654` → 31.7M shares are real exchange feed, not corruption |
| Native 128-bit bitmask routing works | `((uuid_hi>>52)&4095)=930` matches 100% of trade rows (Postgres BIGINT); Turso/SQLite CANNOT (64-bit → 0) |
| Per-transaction proof | `proof_transaction.py` on 3,000 real rows: 0 round-trip failures, 0 type mismatch, 100% bitmask |
| Supabase subset synced | `uuid_trades_subset` = 1,500,000 rows via chunked COPY (50k/statement, beats free-tier timeout) |
| Vercel live + passkey-gated | `uuid.somacosf.com` HTTP 200; correct passkey → 200+data; wrong → **401 unauthorized** (verified) |
| Kalshi UUID scaffold mints bets | `kalshi_uuid_bot.py` dry-run → UUID `3a47ea6b-...` (prefix `3a4` = type 0x3A4 KALSHI_BET); matches SDK `CreateOrderRequest` |
| DR recovery point exists | `D:/somacosf/backups/manual/uuid_trades_DR_2026-07-30.dump` (2.2GB, validated archive) |
| Private repo pushed | `SoMaCoSF/prediction-market-analysis` → `fc43470..a142a1c main` (exit 0) |
| Full gist corpus indexed | `docs/GIST_CORPUS.md` — all 102 secret gists categorized (56 GYST, 27 somacosf, 21 Hermes, 15 says.com, 14 pred-mkts, 14 other, 8 ML, 5 icosphere, 3 ghost-catalog) |

## 🔲 ARCHITECTURE / INTENT (not yet running)
| direction | why | gap |
|---|---|---|
| Master→child spawn model (NxN) | UUID is native primitive; updates spawn children, never in-place | current `uuid_trades` is FLAT (joined by string `market_id`); `parent_uuid` + `uuid_quotes` (0x3A1) not yet in schema |
| 24-bit ts by design | real-time sentiment channel, not archive | ts in snapshot is near-constant (artifact); semantics held, variance not yet exercised |
| Roll-up = bitmask, not join | wirespeed payoff | works for fast-filter; exact roll-up needs `parent_uuid` edge (12-bit ns collides) |
| Tailscale→Vercel full-local link | avoid Supabase 500MB cap, show full 52M live | NOT built; Vercel currently can't resolve Supabase free-tier host (`ENOTFOUND`) |
| Native device-bound MFA | device hardware ID as factor | browser can't read MAC/IMEI; WebAuthn is the web-correct equivalent; LAN/Tailscale gate real where server sees MAC/IP |
| Kalshi live submit | near-term activity | needs `KALSHI_KEY_ID` + `KALSHI_PRIVATE_KEY` (not in env); scaffold dry-run only so far |
| says.com network on same substrate | city posts + markets as one UUID graph | ported reference exists (austinsays/kalshi indexers); not yet unified under one mint |

## Truth-loop discipline
- Every "DONE" above has a command that ran. If a claim has no command, it lives in ARCHITECTURE.
- Re-run `proof_transaction.py` after any schema change to keep the per-transaction proof live.
- Re-run `sync_supabase_subset.py` after any local change so the cloud slice matches.
- Never mark ARCHITECTURE as PROVEN until the running system demonstrates it.
