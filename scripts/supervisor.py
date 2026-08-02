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
import runlog  # noqa: E402

PY = ROOT / ".venv311" / "Scripts" / "python.exe"
LOGDIR = ROOT / "logs"
LOGDIR.mkdir(exist_ok=True)

DAEMONS = {
    "mc": "scripts/mission_control.py",
    "scalp": "scripts/profit_scalp.py",
    "chaos": "scripts/chaos_monkey.py",
    "ingest": "scripts/uuid_ingest.py",
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
    return p is not None and p.poll() is None


def can_relaunch(name: str) -> bool:
    now = time.time()
    relaunches[name] = [t for t in relaunches[name] if now - t < 3600]
    return len(relaunches[name]) < MAX_RELAUNCH_PER_HOUR


def main():
    runlog.log_event("supervisor", "watchdog start", daemons=list(DAEMONS))
    for name in DAEMONS:
        spawn(name)
        time.sleep(2)
    last_beat = 0
    while True:
        time.sleep(POLL_S)
        for name in DAEMONS:
            if not alive(name):
                p = procs.get(name)
                code = p.poll() if p else "none"
                runlog.log_event("supervisor", f"{name} DEAD (exit={code})", exit=code)
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
            last_beat = time.time()


if __name__ == "__main__":
    sys.exit(main())
