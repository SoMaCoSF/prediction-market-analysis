# file_id: SOM-PY-0944-v1.0.0 name: fleetlib.py description: Fleet sanity — singleton locks (refuse double-run) + checkin heartbeats (stale = hung = supervisor restarts); the checkin sanity loop project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [fleet, singleton, heartbeat, sanity, supervisor] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""fleetlib.py — the checkin sanity loop.

acquire_lock(name): take logs/<name>.lock (pid inside). If a LIVE pid already
holds it, print and sys.exit(0) — duplicates die at birth. This kills the
runaway-fleet failure class at the source.

checkin(name): refresh logs/<name>.heartbeat each loop iteration. The
supervisor treats a stale heartbeat (>180s) in a live process as HUNG and
restarts it; a dead process restarts as before. Daemons must check in to live.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGDIR = ROOT / "logs"
LOGDIR.mkdir(exist_ok=True)


def _pid_alive(pid: int) -> bool:
    """True if pid is a live process. Windows: tasklist; POSIX: os.kill(pid, 0)."""
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            return str(pid) in out
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def acquire_lock(name: str) -> None:
    lock = LOGDIR / f"{name}.lock"
    if lock.exists():
        try:
            pid = int(lock.read_text().strip())
        except Exception:
            pid = -1
        if _pid_alive(pid):
            print(f"[{name}] another instance alive (pid={pid}) — refusing to double-run", flush=True)
            sys.exit(0)
    # atomic create — simultaneous boots can't both win
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            pid = int(lock.read_text().strip())
        except Exception:
            pid = -1
        if _pid_alive(pid):
            print(f"[{name}] another instance alive (pid={pid}) — refusing to double-run", flush=True)
            sys.exit(0)
        fd = os.open(str(lock), os.O_WRONLY | os.O_TRUNC)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)


def checkin(name: str) -> None:
    try:
        (LOGDIR / f"{name}.heartbeat").write_text(str(time.time()))
    except Exception:
        pass


def heartbeat_age(name: str) -> float:
    try:
        return time.time() - float((LOGDIR / f"{name}.heartbeat").read_text().strip())
    except Exception:
        return 1e9
