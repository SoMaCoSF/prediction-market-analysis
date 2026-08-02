<!-- =============================================================================== file_id: SOM-DOC-0921-v1.0.0 name: TRADING_CONTROL.md description: Runbook for the UUID-native Kalshi trading system — architecture, boot order, mission control, passkey, caps, go-live checklist project_id: PREDICTION-MARKET-ANALYSIS category: doc tags: [runbook, trading, mission-control, kalshi, uuid] created: 2026-08-02 modified: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT =============================================================================== -->

# SOMACO UUID TRADER — Control Runbook

Every market event **is** a GYST UUIDv8. The trading ledger reconciles itself by
construction: `client_order_id` = the order UUID's low-42 tail, so every exchange
ack resolves by one bitmask — no lookup table.

## Architecture

```
Kalshi WS/REST ──► mint 0x3A4 order (child of 0x3B0 market) ──► Supabase PG ledger
                      │ client_order_id = low-42 tail              (uuid_orders / uuid_fills /
                      ▼                                            uuid_positions / uuid_marks /
              RSA-PSS signed POST                                 uuid_pnl view)
              /portfolio/orders ──► ack echoes coi ──► bitmask reconcile
                                                        (uuid_lo & 2^42-1)
Local PG (52.77M trades) = analytics corpus · Supabase PG = shared trading ledger SoT
Mission control (FastAPI :8420) and the Vercel app both read/write Supabase.
```

## Repo map (trading path)

| File | Role |
|---|---|
| `scripts/uuid_service_turboquant.py` | Canonical GYST encoder/decoder (deterministic low-42 via `_content42`, optional `content_seed`) |
| `scripts/verify_encoder.py` | 14-check encoder proof (`ALL OK` required) |
| `scripts/uuid_ledger.py` | Ledger module: mint order/fill/mark children, reconcile, positions, P&L rollup |
| `scripts/ledger_schema.sql` | Ledger DDL (idempotent) — applied to local PG **and** Supabase |
| `scripts/proof_ledger.py` | 15-check ledger proof, rolled-back txn (`LEDGER VERIFIED` required) |
| `scripts/sb.py` | Supabase conn from `.env_turso` (never prints secrets) |
| `scripts/kalshi_uuid_bot.py` | CLI order path (dry-run default; real submit via kalshi_python 2.1.x) |
| `scripts/mission_control.py` | Web terminal: stats/markets/ticket/kill switch on `:8420` |
| `scripts/mc_static/index.html` | Mission control UI (terminal UX) |
| `scripts/proof_transaction.py` | Corpus proof: 3000/3000 round-trip on live 52.77M rows |

## Boot order

1. **Local PG** (analytics corpus): must be launched detached from PowerShell —
   launching from MSYS/bash makes backends crash with `0xC0000142` on connect.
   ```powershell
   Start-Process -FilePath '.pg/pg16/pgsql/bin/postgres.exe' -ArgumentList '-D','.pg/data' -WindowStyle Hidden
   ```
2. **Mission control**:
   ```bash
   .venv311/Scripts/python scripts/mission_control.py   # http://127.0.0.1:8420
   ```
3. Proofs (any time): `verify_encoder.py`, `proof_ledger.py`, `proof_transaction.py`.

## Passkey

One passkey across local MC + the Vercel app:
`sha256("3024a97f6e32|omen-01|" + STATUS_SALT)` (STATUS_SALT in `.env_turso`).
Required for PAPER and LIVE order posts and the kill switch. Read-only views are open.

## Risk gates (hard-coded)

- count ≤ 5 contracts/order · notional ≤ $5/order
- LIVE requires `confirm=FIRE` + keys present + kill switch disengaged
- Kill switch = presence of `.mc_kill` (instant block, HTTP 423)

## Go-live checklist (Phase 3)

1. `.kalshi_key.pem` (gitignored) + `KALSHI_KEY_ID` in `.env` — user places, never in chat
2. `verify_encoder.py` ALL OK · `proof_ledger.py` VERIFIED · corpus online
3. First live trade: 1 contract, top-volume market, watch ack → ledger `submitted`
4. Fill poller reconciles via `client_order_id`; settle → `uuid_marks` → realized P&L

## Phase status

- **Phase 0** consolidate: ✅ (encoder deterministic, SDK installed, proofs green)
- **Phase 1** ledger: ✅ (schema local+Supabase, 15/15 proof, e2e loop green)
- **Phase 2** paper gate: 🔶 infra ready (paper fills through MC); needs 60+ resolved @ >55%
- **Phase 3** go-live: ⛔ awaiting user keys + explicit GO
