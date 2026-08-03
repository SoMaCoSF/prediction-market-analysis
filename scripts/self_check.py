# file_id: SOM-PY-0943-v1.0.0 name: self_check.py description: Full system self-check — fleet liveness, exchange auth/state, ledger truth, runlog assertions, stream freshness, git state; one call, zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [self-check, diagnostics, fleet, exchange, zero-token] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""self_check.py — the whole system, one report. PYTHONPATH= .venv311/Scripts/python.exe scripts/self_check.py"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import httpx  # noqa: E402
import sb  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
OK, WARN, BAD = "OK  ", "WARN", "FAIL"


def line(status, msg):
    print(f"  [{status}] {msg}")


def _sign(method, path, ts):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key((ROOT / ".kalshi_key.pem").read_bytes(), password=None)
    sig = key.sign(f"{ts}{method}{path}".encode(),
                   padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                   hashes.SHA256())
    return base64.b64encode(sig).decode()


def kget(path):
    try:
        ts = str(int(time.time() * 1000))
        full = "/trade-api/v2" + path.split("?")[0]
        h = {"KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"),
             "KALSHI-ACCESS-SIGNATURE": _sign("GET", full, ts),
             "KALSHI-ACCESS-TIMESTAMP": ts}
        r = httpx.get(KALSHI + path, headers=h, timeout=15)
        if r.status_code == 200:
            return r.json(), None
        return None, f"HTTP {r.status_code}"
    except Exception as e:
        return None, repr(e)[:70]


def main():
    print("=" * 74)
    print(f"SELF-CHECK {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 74)

    print("\n[1] FLEET (daemon processes)")
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -match 'mission_control|profit_scalp|chaos_monkey|uuid_ingest|fill_poller|supervisor' } | "
             "ForEach-Object { \"$($_.ProcessId)|$($_.ParentProcessId)|$($_.CommandLine)\" }"],
            capture_output=True, text=True, timeout=20).stdout
        procs = []
        pids = set()
        for ln in out.splitlines():
            parts = ln.split("|", 2)
            if len(parts) == 3 and parts[0].strip().isdigit():
                pid, ppid, cmd = int(parts[0]), int(parts[1]), parts[2]
                procs.append((pid, ppid, cmd))
                pids.add(pid)
        # uv venv pairs share an identical command line as parent->child.
        # Real dupes are siblings. Count "roots" inside each cmdline set:
        # a venv pair roots once; true dupes root per sibling.
        for name, script in [("supervisor", "supervisor.py"), ("mc", "mission_control.py"), ("scalp", "profit_scalp.py"),
                             ("chaos", "chaos_monkey.py"), ("ingest", "uuid_ingest.py"), ("fills", "fill_poller.py")]:
            members = [(pid, ppid) for (pid, ppid, cmd) in procs if script in cmd]
            member_pids = {pid for pid, _ in members}
            n = sum(1 for pid, ppid in members if ppid not in member_pids)
            line(OK if n == 1 else (WARN if n > 1 else BAD), f"{name:10s} {'running' if n==1 else ('x'+str(n)+' (dupes!)' if n>1 else 'NOT RUNNING')}")
    except Exception as e:
        line(WARN, f"process enumeration failed: {repr(e)[:60]}")

    print("\n[2] MISSION CONTROL")
    try:
        s = httpx.get("http://127.0.0.1:8420/api/stats", timeout=8).json()
        line(OK, f"api/stats: keys={s.get('keys')} kill={s.get('kill')} corpus={s.get('corpus',{}).get('online')}")
        led = s.get("ledger", {})
        line(OK, f"ledger: orders={led.get('orders')} fills={led.get('fills')} realized={led.get('realized_pnl_cents')}c")
    except Exception as e:
        line(BAD, f"MC unreachable: {repr(e)[:60]}")

    print("\n[3] EXCHANGE (Kalshi auth + account state)")
    bal, err = kget("/portfolio/balance")
    if bal:
        line(OK, f"auth OK — cash ${bal.get('balance_dollars')} portfolio_value {bal.get('portfolio_value')}")
        bb = bal.get("balance_breakdown") or []
        for b in bb[:3]:
            print(f"        breakdown: {b}")
    else:
        line(BAD, f"balance call failed: {err} (auth/connectivity)")
    pos, err = kget("/portfolio/positions?limit=100")
    if pos is not None:
        n = sum(1 for mp in pos.get("market_positions", []) if float(mp.get("position_fp") or 0) != 0)
        line(OK, f"{n} open positions")
    else:
        line(WARN, f"positions call failed: {err}")
    fills, err = kget("/portfolio/fills?limit=5")
    if fills is not None:
        line(OK, f"fills endpoint OK ({len(fills.get('fills') or [])} recent)")
    else:
        line(WARN, f"fills call failed: {err}")

    print("\n[4] LEDGER (Supabase)")
    try:
        con = sb.sb_conn()
        cur = con.cursor()
        for t in ["uuid_orders", "uuid_acks", "uuid_fills", "uuid_positions"]:
            cur.execute(f"SELECT count(*) FROM {t}")
            line(OK, f"{t}: {cur.fetchone()[0]} rows")
        cur.execute("SELECT coalesce(sum(realized_pnl_cents),0) FROM uuid_positions")
        line(OK, f"realized P&L: {cur.fetchone()[0]}c")
        con.close()
    except Exception as e:
        line(BAD, f"ledger read failed: {repr(e)[:70]}")

    print("\n[5] RUNLOG (events + assertions)")
    evts = []
    for f in (ROOT / "logs").glob("run_*.jsonl"):
        for ln in f.read_text(errors="ignore").splitlines():
            try:
                evts.append(json.loads(ln))
            except Exception:
                pass
    line(OK, f"{len(evts)} events")
    fails = [e for e in evts if e.get("kind") == "assert" and not e.get("pass")]
    line(OK if not fails else BAD, f"assertions failed: {len(fails)}")
    for e in fails[:5]:
        print(f"        !! {e.get('t')} [{e.get('actor')}] {e.get('msg')}")
    now = time.time()
    for actor in ["supervisor", "mc", "scalp", "chaos", "ingest", "fills"]:
        recent = [e for e in evts if e.get("actor") == actor]
        if not recent:
            line(WARN, f"{actor:10s} no events yet")
        else:
            age = now - max(e.get("ts", 0) for e in recent)
            line(OK if age < 420 else WARN, f"{actor:10s} last event {age/60:.0f} min ago")

    print("\n[6] UUID STREAM")
    try:
        import sqlite3
        scon = sqlite3.connect(ROOT / "data" / "uuid_stream.db")
        n = scon.execute("SELECT count(*) FROM stream").fetchone()[0]
        mx = scon.execute("SELECT max(ts) FROM stream").fetchone()[0]
        age = (time.time() - (mx or 0)) / 60
        scon.close()
        line(OK if age < 2 else WARN, f"{n} rows, freshest {age:.1f} min ago")
    except Exception as e:
        line(WARN, f"stream read: {repr(e)[:50]}")

    print("\n[7] GIT")
    try:
        st = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, cwd=ROOT, timeout=15).stdout.strip()
        line(OK if not st else WARN, "clean tree" if not st else f"{len(st.splitlines())} uncommitted paths")
        lg = subprocess.run(["git", "log", "--oneline", "-1"], capture_output=True, text=True, cwd=ROOT, timeout=15).stdout.strip()
        print(f"        HEAD: {lg}")
    except Exception as e:
        line(WARN, f"git: {repr(e)[:50]}")
    print("\n" + "=" * 74)


if __name__ == "__main__":
    sys.exit(main())
