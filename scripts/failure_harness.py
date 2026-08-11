#!/usr/bin/env python3
# file_id: SOM-PY-1006-v1.0.0 name: failure_harness.py description: Event-feed/trade failure harness — detects dead event feed, dead trading daemons, and dead MC; auto-restarts and logs failure signatures project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [harness, watchdog, failure, restart, daemons, events] created: 2026-08-11 version: 1.0.0 agent_id: HERMES-AGENT
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(".").resolve()
LOGS = ROOT / "logs"
HARNESS_LOG = LOGS / "harness.out.log"
STATE_FILE = ROOT / ".harness_state.json"

TRADING_DAEMONS = [
    "whale_copier.py",
    "shadow_index.py",
    "news_supply_engine.py",
    "crossvenue_engine.py",
]

def log(msg: str):
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}"
    print(line, flush=True)
    with open(HARNESS_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def load_state():
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except Exception:
        pass
    return {"restarts": {}, "feed_zero_since": None, "mc_dead_since": None}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state))

def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

def read_lock(daemon: str):
    lock = LOGS / f"{daemon}.lock"
    if not lock.exists():
        return None
    try:
        return int(lock.read_text().strip())
    except Exception:
        return None

def check_event_feed():
    try:
        import sb as sb_mod
        con = sb_mod.sb_conn()
        cur = con.cursor()
        cur.execute("SELECT k, v, updated_at FROM mc_state WHERE k IN ('shadow:latest','xvenue:latest','poly:latest','time:articles','copier:board','uptick:spiral') ORDER BY k")
        rows = cur.fetchall()
        now = time.time()
        stale = []
        empty = []
        for k, v, upd in rows:
            age = now - upd.timestamp()
            try:
                data = json.loads(v or "[]")
                count = len(data) if isinstance(data, list) else 1
            except Exception:
                count = 0
            if count == 0:
                empty.append(k)
            if age > 180:
                stale.append(f"{k}={age:.0f}s")
        cur.close()
        con.close()
        return empty, stale
    except Exception as e:
        return [f"events_error:{e}"], []

def check_mc():
    import urllib.request
    try:
        req = urllib.request.Request("http://127.0.0.1:8420/api/stats", method="GET")
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False

def check_daemon_processes():
    dead = []
    for daemon in TRADING_DAEMONS:
        name = daemon.replace(".py", "")
        pid = read_lock(name)
        if pid is None or not is_pid_alive(pid):
            dead.append(name)
    return dead

def start_daemon(script: str):
    cmd = [sys.executable, script]
    log_file = LOGS / f"{Path(script).stem}.out.log"
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=open(log_file, "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
        log(f"STARTED {script} pid={proc.pid}")
        return proc.pid
    except Exception as e:
        log(f"START FAILED {script}: {e}")
        return None

def maybe_start(name: str, state: dict):
    pid = read_lock(name)
    if pid and is_pid_alive(pid):
        return False
    new_pid = start_daemon(f"scripts/{name}.py")
    if new_pid:
        state["restarts"][name] = state["restarts"].get(name, [])[-4:] + [time.time()]
        save_state(state)
        return True
    return False

def main():
    LOGS.mkdir(exist_ok=True)
    log("harness tick")
    state = load_state()
    now = time.time()

    mc_alive = check_mc()
    if not mc_alive:
        if state.get("mc_dead_since") is None:
            state["mc_dead_since"] = now
            save_state(state)
        age = now - state["mc_dead_since"]
        log(f"FAILURE: MC dead for {age:.0f}s")
        if age > 10:
            log("ACTION: restarting mission_control.py")
            start_daemon("scripts/mission_control.py")
            state["mc_dead_since"] = now
            save_state(state)
    else:
        if state.get("mc_dead_since") is not None:
            log("RECOVERY: MC is back")
        state["mc_dead_since"] = None
        save_state(state)

    empty, stale = check_event_feed()
    restarted = set()
    if empty or stale:
        if state.get("feed_zero_since") is None:
            state["feed_zero_since"] = now
            save_state(state)
        age = now - state["feed_zero_since"]
        log(f"FAILURE: event feed unhealthy for {age:.0f}s empty={empty} stale={stale}")
        if age > 30:
            dead = check_daemon_processes()
            if dead:
                log(f"ACTION: dead trading daemons={dead} — restarting")
                for name in dead:
                    if maybe_start(name, state):
                        restarted.add(name)
            state["feed_zero_since"] = now
            save_state(state)
    else:
        if state.get("feed_zero_since") is not None:
            log("RECOVERY: event feed healthy")
        state["feed_zero_since"] = None
        save_state(state)

    dead = check_daemon_processes()
    if dead:
        log(f"FAILURE: dead trading daemons={dead}")
        for name in dead:
            if name in restarted:
                continue
            if maybe_start(name, state):
                pass
            else:
                log(f"WARN: could not restart {name}")

if __name__ == "__main__":
    main()
