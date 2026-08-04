# file_id: SOM-PY-0995-v1.0.0 name: agent_status.py description: Agent status publisher — aggregates fleet liveness, governor, equity, last commit, and data/agent_now.md into mc_state hermes:status every 60s; time.somacosf.com renders it as the agent source of truth; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [status, agent, transparency, fleet, zero-token] created: 2026-08-04 version: 1.0.0 agent_id: HERMES-AGENT
"""agent_status.py — what the agent is doing, published.

time.somacosf.com reads mc_state 'hermes:status' — the user watches pages,
not chat. The daemon aggregates machine state; data/agent_now.md carries the
agent's own current-task note (written by the agent when tasks shift).
Zero model tokens.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import runlog  # noqa: E402
import sb  # noqa: E402
from run_report import kget  # noqa: E402

NOW_MD = ROOT / "data" / "agent_now.md"
POLL_S = 60

LANES = ["supervisor", "governor", "mc", "scalp", "btctrend", "trend-eth", "trend-sol",
         "trend-xrp", "trend-doge", "copier", "ws", "tick", "xvenue", "calendar", "shadow",
         "maker", "news", "sweep", "evidence", "xwatch", "ingest", "fills", "vault", "promoter"]


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] [agent-status] {m}", flush=True)
    runlog.log_event("agent_status", m)


def main():
    fleetlib.acquire_lock("agent-status")
    log("start | publishing hermes:status every 60s")
    while True:
        try:
            fleetlib.checkin("agent-status")
            b = kget("/portfolio/balance")
            cash = float(b.get("balance_dollars") or 0)
            eq = cash + (b.get("portfolio_value") or 0) / 100
            alive = [n for n in LANES if fleetlib.heartbeat_age(n) < 400]
            now_note = NOW_MD.read_text(encoding="utf-8").strip()[:500] if NOW_MD.exists() else ""
            try:
                commit = subprocess.run(["git", "log", "--oneline", "-1"], capture_output=True,
                                        text=True, timeout=10, cwd=str(ROOT)).stdout.strip()
            except Exception:
                commit = ""
            con = sb.sb_conn()
            con.autocommit = True
            con.cursor().execute(
                "INSERT INTO mc_state (k, v, updated_at) VALUES ('hermes:status', %s, now()) "
                "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
                (json.dumps({
                    "equity": round(eq, 2), "cash": round(cash, 2),
                    "fleet_alive": len(alive), "fleet_total": len(LANES),
                    "fleet_down": [n for n in LANES if n not in alive],
                    "now": now_note, "commit": commit, "ts": int(time.time()),
                }),))
            con.close()
        except Exception as e:
            log(f"warn {repr(e)[:60]}")
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
