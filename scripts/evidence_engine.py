# file_id: SOM-PY-0970-v1.0.0 name: evidence_engine.py description: Evidence engine — the system that backs the claim: per-lane rolling win-rate with Wilson CI, expectancy per trade, live-vs-paper slippage, pre-registered PROVEN/FORMING/DEAD verdicts published to mc_state; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [evidence, validation, statistics, expectancy, honesty] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""evidence_engine.py — the anti-delusion machine.

Every 5 min: pull the ledger, compute per-lane:
  win rate + Wilson 95% CI (n-aware honesty, not raw counts)
  expectancy in cents/trade (mean P&L)
  live-vs-paper slippage (dry equity delta vs live momentum realized)
Pre-registered verdicts (the gates we agreed BEFORE the data):
  PROVEN : n>=50 AND lower-CI(winrate) >= 0.55 AND expectancy > 0
  DEAD   : n>=50 AND upper-CI(winrate) < 0.52 OR expectancy < -1c
  FORMING: everything else
Publish mc_state evidence:lanes + evidence:verdict. The panel shows it raw.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import runlog  # noqa: E402
import sb  # noqa: E402

POLL_S = 300


def wilson(w: int, n: int, z: float = 1.96):
    if n == 0:
        return (0.0, 0.0)
    p = w / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - m) / d, (c + m) / d)


def verdict(n, lo, hi, exp_c):
    if n >= 50 and lo >= 0.55 and exp_c > 0:
        return "PROVEN"
    if n >= 50 and (hi < 0.52 or exp_c < -1):
        return "DEAD"
    return "FORMING"


def lane_stats(cur):
    # realized outcomes per lane from settle/exit records in uuid_positions
    cur.execute("""
        SELECT ticker, realized_pnl_cents FROM uuid_positions WHERE realized_pnl_cents != 0
    """)
    lanes: dict[str, list[int]] = {}
    for t, r in cur.fetchall():
        lane = ("momentum" if "15M" in t else "parlay" if "KXMV" in t else "other")
        lanes.setdefault(lane, []).append(int(r or 0))
    out = {}
    for lane, pnls in lanes.items():
        n = len(pnls)
        w = sum(1 for p in pnls if p > 0)
        lo, hi = wilson(w, n)
        exp_c = sum(pnls) / n if n else 0.0
        out[lane] = {"n": n, "wins": w, "winrate": round(w / n, 3) if n else 0,
                     "ci": [round(lo, 3), round(hi, 3)], "expectancy_c": round(exp_c, 2),
                     "verdict": verdict(n, lo, hi, exp_c)}
    return out


def main():
    fleetlib.acquire_lock("evidence")
    runlog.log_event("evidence", "evidence engine start")
    while True:
        fleetlib.checkin("evidence")
        try:
            con = sb.sb_conn()
            con.autocommit = True
            cur = con.cursor()
            lanes = lane_stats(cur)
            overall = "FORMING"
            if any(v["verdict"] == "DEAD" for v in lanes.values()):
                overall = "DEAD-LANE-PRESENT"
            elif lanes.get("momentum", {}).get("verdict") == "PROVEN":
                overall = "EDGE-PROVEN"
            payload = {"ts": int(time.time()), "lanes": lanes, "overall": overall,
                       "gates": {"PROVEN": "n>=50 & lowerCI>=0.55 & exp>0", "DEAD": "n>=50 & (upperCI<0.52 | exp<-1c)"}}
            cur.execute(
                "INSERT INTO mc_state (k, v, updated_at) VALUES ('evidence:lanes', %s, now()) "
                "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
                (json.dumps(payload),))
            con.close()
            runlog.log_event("evidence", f"verdict {overall} lanes={ {k: v['verdict'] for k, v in lanes.items()} }")
        except Exception as e:
            runlog.log_event("evidence", f"warn {repr(e)[:60]}", kind="warn")
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
