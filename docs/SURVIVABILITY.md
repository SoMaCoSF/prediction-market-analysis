# file_id: SOM-DOC-0975-v1.0.0 name: docs/SURVIVABILITY.md description: Survivability runbook — what keeps the system alive and how to rebuild from total loss project_id: PREDICTION-MARKET-ANALYSIS category: doc tags: [survivability, runbook, recovery, durability] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT

# SURVIVABILITY — the system cannot go away

## What survives what

| Failure | What survives | Recovery |
|---|---|---|
| Chat session dies | Everything | Watchdog task restarts supervisor every 5 min |
| Daemon crash | Fleet | Supervisor relaunches (6/hr cap, crash-only) |
| Windows reboot | Everything | `SoMaCo-Fleet` task fires at logon |
| Local box total loss | Code (GitHub private repo) + ledger (Supabase) + cloud panels (Vercel) | Rebuild below |
| Vercel down | Local MC on :8420 | Panels redeploy from repo |

## Layer inventory
- **Code**: `SoMaCoS/uuid-trader` private repo, pushed every commit.
- **Ledger SoT**: Supabase (orders/acks/fills/positions/mc_state) — cloud, durable.
- **Fleet persistence**: Task Scheduler `SoMaCo-Fleet` (logon) + `SoMaCo-Fleet-Watch` (every 5 min). Atomic locks make duplicate launches harmless.
- **Observability without the model**: `run_report.py`, `self_check.py`, `lanes_report.py` — zero tokens.
- **Secrets (the ONE unrecoverable piece)**: `.kalshi_key.pem` + `.env` are LOCAL ONLY by design. **User must keep these in a password manager / second machine.** Without them the trading stops; everything else self-heals.

## Total-loss rebuild (new box, ~10 min)
1. `git clone` the private repo
2. `uv venv .venv311 && uv pip install -r scripts/_deps_core.txt`
3. Restore `.env` + `.kalshi_key.pem` from the password manager
4. `powershell scripts/install_watchdog.ps1`
5. Log off/on (or start the task manually) — fleet self-assembles, supervisor adopts/spawns, ledger resumes from Supabase state.

## Kill / pause
- Kill switch: trade panel → ENGAGE KILL SWITCH (all live orders block).
- Stop fleet: delete the two scheduled tasks + kill python daemons.
