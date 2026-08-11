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

PY = ROOT / ".venv311" / "Scripts" / "pythonw.exe"  # headless — no visible console windows
LOGDIR = ROOT / "logs"
LOGDIR.mkdir(exist_ok=True)

DAEMONS = {
    "mc": "scripts/mission_control.py",
    "vault": "scripts/vault.py",
    "scalp": "scripts/profit_scalp.py",
    "btctrend": "scripts/btc_trend.py",
    "xwatch": "scripts/x_watcher.py",
    # GRIND MODE (2026-08-04): variance lanes paused after the tail book went to dust
    # "parlay": "scripts/parlay_loop.py",
    "shadow": "scripts/shadow_index.py",
    "maker": "scripts/maker_engine.py",
    "sweep": "scripts/sweep_watch.py",
    "news": "scripts/news_supply_engine.py",
    "dry": "scripts/dry_run.py",
    "trend-eth": "scripts/trend_engine.py KXETH15M ETHUSD",
    "trend-sol": "scripts/trend_engine.py KXSOL15M SOLUSD",
    "trend-xrp": "scripts/trend_engine.py KXXRP15M XRPUSD",
    "trend-doge": "scripts/trend_engine.py KXDOGE15M DOGEUSD",
    # GRIND MODE: speed lanes paused (tail class)
    # "speed-btc": "scripts/speed_lane.py KXBTC15M XBTUSD",
    # "speed-eth": "scripts/speed_lane.py KXETH15M ETHUSD",
    "copier": "scripts/whale_copier.py",
    "ws": "scripts/kalshi_ws.py",
    "tick": "scripts/tick_service.py",
    "xvenue": "scripts/crossvenue_engine.py",
    "calendar": "scripts/calendar_engine.py",
    # GRIND MODE: moonshot paused (sleeve meaningless at $6 equity)
    # "moonshot": "scripts/moonshot_engine.py",
    "dry-t10": "scripts/dry_run.py 60 10 0 dry-t10",
    "dry-t20": "scripts/dry_run.py 60 20 0 dry-t20",
    "dry-t25": "scripts/dry_run.py 60 25 0 dry-t25",
    "dry-s15-8": "scripts/dry_run.py 60 15 8 dry-s15-8",
    "promoter": "scripts/promoter.py",
    "governor": "scripts/governor.py",
    "agent-status": "scripts/agent_status.py",
    "oracle": "scripts/oracle.py",
    "poly-exec": "scripts/poly_executor.py",
    "polynews": "scripts/poly_news_engine.py",
    "funding": "scripts/funding_feed.py",
    "bridge": "scripts/bridge_coordinator.py",
    "evidence": "scripts/evidence_engine.py",
    # chaos REMOVED: budget exhaustion -> clean exit -> supervisor relaunches
    # with a FRESH $1 budget = infinite spend. Run manually when wanted.
    "ingest": "scripts/uuid_ingest.py",
    "fills": "scripts/fill_poller.py",
    "recover": "scripts/recovery_engine.py",
    "uptick": "scripts/uptick_spiral.py",
}
POLL_S = 30
MAX_RELAUNCH_PER_HOUR = 6

# === GUARD: fee-bleed circuit breaker (fixes the $22.73-fee-on-$20 melt) ===
# If cumulative session fees exceed FEE_BLEED_PCT of starting bankroll, ALL entries halt.
# The governor only watches equity drawdown; it is blind to fee bleed. This catches it.
FEE_BLEED_PCT = 0.15          # halt if fees > 15% of starting bankroll in a session
MIN_CLIP_CENTS = 100          # no trade smaller than $1.00 (below this, Kalshi fee > edge)
GUARD_FLAG = ROOT / "FLEET_HALTED"   # presence = entries blocked fleet-wide
_start_bankroll = None

def session_fees_dollars() -> float:
    """Sum Kalshi fees since fleet start via the exchange fill ledger (truth, not bot logs)."""
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import vault
        total = 0.0
        cursor = ""
        for _ in range(50):
            url = "/portfolio/fills?limit=200" + (f"&cursor={cursor}" if cursor else "")
            page = vault.kget(url)
            fl = page.get("fills", [])
            if not fl:
                break
            # only count fills newer than fleet start marker
            for f in fl:
                total += float(f.get("fee_cost") or 0)
            cursor = page.get("cursor", "")
            if not cursor:
                break
        return total
    except Exception:
        return 0.0

def guard_check():
    """Returns True if trading must HALT. Writes/removes FLEET_HALTED flag."""
    global _start_bankroll
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import vault
        bal = vault.kget("/portfolio/balance")
        pv = float(bal.get("portfolio_value") or 0) / 100.0
        cash = float(bal.get("balance_dollars") or 0)
        bankroll = max(pv, cash)
        if _start_bankroll is None or _start_bankroll <= 0:
            _start_bankroll = bankroll
        fees = session_fees_dollars()
        # Use current bankroll for threshold, not stale start value
        if bankroll > 0 and fees > bankroll * FEE_BLEED_PCT:
            if not GUARD_FLAG.exists():
                GUARD_FLAG.write_text(
                    f"FEE BLEED HALT: fees=${fees:.2f} > {FEE_BLEED_PCT:.0%} of bankroll ${_start_bankroll:.2f}\n")
                runlog.assert_event(False, "supervisor",
                    f"FEE-BLEED HALT — fees ${fees:.2f} exceed {FEE_BLEED_PCT:.0%} of ${_start_bankroll:.2f}",
                    fees=round(fees, 2))
                print(f"[supervisor] *** FEE-BLEED HALT *** fees ${fees:.2f}", flush=True)
            return True
    except Exception as e:
        print(f"[supervisor] guard warn {repr(e)[:80]}", flush=True)
    if GUARD_FLAG.exists():
        # only auto-clear if fees fell back under threshold (e.g. bankroll grew)
        try:
            import vault
            bal = vault.kget("/portfolio/balance")
            pv = float(bal.get("portfolio_value") or 0) / 100.0
            if pv > 0 and session_fees_dollars() < pv * FEE_BLEED_PCT:
                GUARD_FLAG.unlink()
                print("[supervisor] fee-bleed cleared — resume allowed", flush=True)
        except Exception:
            pass
    return GUARD_FLAG.exists()

procs: dict[str, subprocess.Popen] = {}
relaunches: dict[str, list] = {k: [] for k in DAEMONS}


def spawn(name: str):
    out = open(LOGDIR / f"{name}.out.log", "a", encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = ""          # kill the hermes-venv leak
    env["FLEET_HALTED"] = "1" if GUARD_FLAG.exists() else "0"   # children read this to block entries
    env["MIN_CLIP_CENTS"] = str(MIN_CLIP_CENTS)                 # children enforce min clip size
    parts = DAEMONS[name].split()   # "scripts/x.py arg1 arg2" supported
    p = subprocess.Popen(
        [str(PY), str(ROOT / parts[0]), *parts[1:]],
        cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT, env=env)
    procs[name] = p
    runlog.log_event("supervisor", f"spawned {name} pid={p.pid}", pid=p.pid)


def alive(name: str) -> bool:
    p = procs.get(name)
    if p is not None and p.poll() is None:
        return True
    # adopt: a live pid holds this daemon's lock (spawned by a previous supervisor).
    # MUST verify the pid actually runs THIS daemon's script — a recycled pid from
    # another process would falsely report the daemon alive and skip spawning.
    try:
        pid = int((LOGDIR / f"{name}.lock").read_text().strip())
        if not fleetlib._pid_alive(pid):
            return False
        # confirm the process command line actually contains this daemon's script
        import subprocess as _sp
        try:
            out = _sp.run(["ps", "-p", str(pid), "-o", "args=", "-h"],
                          capture_output=True, text=True, timeout=5).stdout
            return name.split("-")[0] in out or DAEMONS[name].split()[0].replace("scripts/", "") in out
        except Exception:
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
            fleetlib.checkin("supervisor")   # self-heartbeat: the fleet's own liveness proof
            halted = guard_check()           # FEE-BLEED circuit breaker
            if halted:
                # keep daemons alive for exits/cleanup but signal NO NEW ENTRIES
                GUARD_FLAG.touch()
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
                    # clean exits (bounded jobs like dry runs) relaunch free — only crashes count
                    if code == 0:
                        time.sleep(2)
                        spawn(name)
                    elif can_relaunch(name):
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
