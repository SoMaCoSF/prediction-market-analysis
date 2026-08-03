# file_id: SOM-PY-0941-v1.0.0 name: supervisor.py description: Zero-token watchdog — spawns all trading daemons, relaunches any that die (backoff-capped), heartbeats to runlog; the persistence layer project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [supervisor, watchdog, persistence, daemons, zero-token] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""supervisor.py — keep the Kalshi loop alive. Pure Python, zero model tokens.

Spawns each daemon as a subprocess, polls every 30s, relaunches the dead
(max 6 relaunches/daemon/hour, exponential backoff). Child stdout/stderr append
to logs/<name>.out.log. Every (re)launch + heartbeat goes to runlog with an
aliveness assertion. Runs until killed; children die with it (session scope).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import runlog  # noqa: E402

PY = ROOT / ".venv311" / "Scripts" / "python.exe"
LOGDIR = ROOT / "logs"
LOGDIR.mkdir(exist_ok=True)

DAEMONS = {
    "mc": "scripts/mission_control.py",
    "scalp": "scripts/profit_scalp.py",
    "btctrend": "scripts/btc_trend.py",
    "xwatch": "scripts/x_watcher.py",
    "parlay": "scripts/parlay_loop.py",
    "shadow": "scripts/shadow_index.py",
    "maker": "scripts/maker_engine.py",
    # chaos REMOVED: budget exhaustion -> clean exit -> supervisor relaunches
    # with a FRESH $1 budget = infinite spend. Run manually when wanted.
    "ingest": "scripts/uuid_ingest.py",
    "fills": "scripts/fill_poller.py",
}
POLL_S = 30
MAX_RELAUNCH_PER_HOUR = 6

procs: dict[str, subprocess.Popen] = {}
relaunches: dict[str, list] = {k: [] for k in DAEMONS}


def spawn(name: str):
    out = open(LOGDIR / f"{name}.out.log", "a", encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = ""          # kill the hermes-venv leak
    p = subprocess.Popen(
        [str(PY), str(ROOT / DAEMONS[name])],
        cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT, env=env)
    procs[name] = p
    runlog.log_event("supervisor", f"spawned {name} pid={p.pid}", pid=p.pid)


def alive(name: str) -> bool:
    p = procs.get(name)
    if p is not None and p.poll() is None:
        return True
    # adopt: a live pid holds this daemon's lock (spawned by a previous supervisor)
    try:
        pid = int((LOGDIR / f"{name}.lock").read_text().strip())
        return fleetlib._pid_alive(pid)
    except Exception:
        return False


def can_relaunch(name: str) -> bool:
    now = time.time()
    relaunches[name] = [t for t in relaunches[name] if now - t < 3600]
    return len(relaunches[name]) < MAX_RELAUNCH_PER_HOUR


def main():
    fleetlib.acquire_lock("supervisor")
    runlog.log_event("supervisor", "watchdog start", daemons=list(DAEMONS))
    print(f"[supervisor] watchdog start: {list(DAEMONS)}", flush=True)
    for name in DAEMONS:
        if alive(name):
            print(f"[supervisor] {name} already alive — adopting, not spawning", flush=True)
            runlog.log_event("supervisor", f"adopted live {name} (no spawn)", daemon=name)
            continue
        spawn(name)
        print(f"[supervisor] spawned {name} pid={procs[name].pid}", flush=True)
        time.sleep(2)
    last_beat = 0
    while True:
        try:
            time.sleep(POLL_S)
            for name in DAEMONS:
                if alive(name) and fleetlib.heartbeat_age(name) > 180:
                    runlog.log_event("supervisor", f"{name} HUNG (no checkin >180s) — restarting", daemon=name)
                    print(f"[supervisor] {name} HUNG — restarting", flush=True)
                    try:
                        procs[name].kill()
                    except Exception:
                        pass
                    time.sleep(2)
                    spawn(name)
                    continue
                if not alive(name):
                    p = procs.get(name)
                    code = p.poll() if p else "none"
                    runlog.log_event("supervisor", f"{name} DEAD (exit={code})", exit=code)
                    print(f"[supervisor] {name} DEAD exit={code}", flush=True)
                    if can_relaunch(name):
                        relaunches[name].append(time.time())
                        backoff = min(60, 2 ** len(relaunches[name]))
                        runlog.log_event("supervisor", f"relaunching {name} in {backoff}s", backoff=backoff)
                        time.sleep(backoff)
                        spawn(name)
                    else:
                        runlog.assert_event(False, "supervisor", f"{name} relaunch cap reached — staying dead", daemon=name)
            if time.time() - last_beat > 300:
                states = {n: alive(n) for n in DAEMONS}
                runlog.assert_event(all(states.values()), "supervisor", "all daemons alive", **states)
                print(f"[supervisor] heartbeat {states}", flush=True)
                heartbeat()
                last_beat = time.time()
        except Exception as e:
            runlog.log_event("supervisor", f"loop warn {repr(e)[:80]}", kind="warn")
            print(f"[supervisor] loop warn {repr(e)[:80]}", flush=True)
            time.sleep(5)


def heartbeat():
    """Upsert daemon aliveness to Supabase mc_state so the CLOUD terminal can see fleet health."""
    try:
        import sb
        con = sb.sb_conn()
        con.autocommit = True
        cur = con.cursor()
        for n in DAEMONS:
            cur.execute(
                "INSERT INTO mc_state (k, v, updated_at) VALUES (%s, %s, now()) "
                "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
                (f"daemon:{n}", "alive" if alive(n) else "dead"))
        con.close()
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
