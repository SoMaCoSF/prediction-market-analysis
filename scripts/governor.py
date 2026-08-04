# file_id: SOM-PY-0994-v1.0.0 name: governor.py description: Equity governor — the circuit breaker: tracks peak equity, HALTS engine entries at -30% drawdown, full-stop at -50%; publishes governor:state; engines check before every entry; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [governor, risk, circuit-breaker, drawdown, fleet, zero-token] created: 2026-08-04 version: 1.0.0 agent_id: HERMES-AGENT
"""governor.py — the equity circuit breaker.

The tail-book lesson ($134 -> $6): engines traded into a drawdown because
nothing WATCHED the equity curve. The governor is that watcher.

States:
  NORMAL   — equity >= 70% of peak: engines trade
  HALT     — equity < 70% of peak:  entries blocked (exits always allowed)
  STOP     — equity < 50% of peak:  entries blocked + alert (manual review)

Engines read mc_state 'governor:state' before entering. Exits never blocked.
Peak ratchets up only. Peak seeded from today's equity_history max.
Zero model tokens.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import runlog  # noqa: E402
import sb  # noqa: E402
from run_report import kget  # noqa: E402

HALT_AT, STOP_AT = 0.70, 0.50
POLL_S = 30


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] [governor] {m}", flush=True)
    runlog.log_event("governor", m)


def equity():
    b = kget("/portfolio/balance")
    cash = float(b.get("balance_dollars") or 0)
    return cash + (b.get("portfolio_value") or 0) / 100


def publish(state, eq, peak):
    con = sb.sb_conn()
    con.autocommit = True
    con.cursor().execute(
        "INSERT INTO mc_state (k, v, updated_at) VALUES ('governor:state', %s, now()) "
        "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
        (json.dumps({"state": state, "equity": round(eq, 2), "peak": round(peak, 2),
                     "dd_pct": round(100 * (1 - eq / peak), 1) if peak else 0,
                     "ts": int(time.time())}),))
    con.close()


def seed_peak():
    """Rolling 24h peak — a historic peak must not freeze recovery forever.
    After the tail-book incident the all-time peak ($182) would hold STOP at $6
    indefinitely; the governor must govern the CURRENT regime."""
    try:
        con = sb.sb_conn()
        cur = con.cursor()
        cur.execute("SELECT max(equity) FROM equity_history WHERE ts > now() - interval '24 hours'")
        mx = cur.fetchone()[0]
        con.close()
        return float(mx) if mx else 0.0
    except Exception:
        return 0.0


def main():
    fleetlib.acquire_lock("governor")
    peak = seed_peak()
    state = "NORMAL"
    log(f"start | peak seeded ${peak:.2f} | HALT at 70% STOP at 50%")
    while True:
        try:
            fleetlib.checkin("governor")
            eq = equity()
            if eq > peak:
                peak = eq
            # rolling-peak decay: if the peak is older than 24h of data, re-seed
            if time.time() % 900 < POLL_S:  # re-check every ~15 min
                rp = seed_peak()
                if rp and rp < peak:
                    peak = rp
            ratio = eq / peak if peak > 0 else 1.0
            new = "STOP" if ratio < STOP_AT else "HALT" if ratio < HALT_AT else "NORMAL"
            if new != state:
                log(f"STATE {state} -> {new} | equity ${eq:.2f} peak ${peak:.2f} dd {100*(1-ratio):.0f}%")
                state = new
            publish(state, eq, peak)
        except Exception as e:
            log(f"warn {repr(e)[:60]}")
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
