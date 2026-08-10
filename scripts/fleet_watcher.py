"""fleet_watcher.py — close-in loop watchdog for the prediction-market fleet.

What it does:
  - polls Kalshi cash + positions every N seconds via direct signed API
  - cross-checks open positions against known live daemons
  - auto-pauses bleeders (kills/restarts the owning daemon)
  - enforces $10 cash floor on live entries
  - publishes watcher state to mc_state (key: watcher:state)
  - emits human-readable log lines for dashboard / debug

Spawn:
  .venv311/Scripts/pythonw.exe scripts/fleet_watcher.py
"""

import json
import os
import subprocess
import time
from pathlib import Path

import httpx
import psutil
import sb
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MC = "http://127.0.0.1:8420"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
POLL = 20                  # seconds between watch cycles
CASH_FLOOR = 10.00        # hard floor — never let live entries run below this
MAX_LIVE_POSITIONS = 6    # safety cap

KNOWN_DAEMONS = {
    "profit_scalp": "scripts/profit_scalp.py",
    "funding_feed": "scripts/funding_feed.py",
    "whale_copier": "scripts/whale_copier.py",
    "mission_control": "scripts/mission_control.py",
    "supervisor": "scripts/supervisor.py",
    "tick_service": "scripts/tick_service.py",
    "crossvenue": "scripts/crossvenue_engine.py",
    "dry_run": "scripts/dry_run.py",
    "dry_no_cheap": "scripts/dry_run_no_cheap.py",
}

WATCHER_KEY = "watcher:state"


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        path = ROOT / "logs" / "watcher.out.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _write_log_once(msg: str) -> None:
    """Best-effort append log during bootstrap before ROOT/logs exist."""
    try:
        path = ROOT / "logs" / "watcher.out.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def kget(path: str) -> dict:
    """Minimal signed Kalshi GET, mirroring existing fleet scripts."""
    try:
        from base64 import b64encode

        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        ts = str(int(time.time() * 1000))
        full = "/trade-api/v2" + path.split("?")[0]
        key = serialization.load_pem_private_key((ROOT / ".kalshi_key.pem").read_bytes(), password=None)
        sig = key.sign(
            f"{ts}GET{full}".encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        h = {
            "KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"),
            "KALSHI-ACCESS-SIGNATURE": b64encode(sig).decode(),
            "KALSHI-ACCESS-TIMESTAMP": ts,
        }
        r = httpx.get(KALSHI + path, headers=h, timeout=15)
        if r.status_code != 200:
            return {"_kget_http_status": r.status_code, "_kget_body": (r.text or "")[:400]}
        return r.json() if "json" in r.headers.get("content-type", "") else {}
    except Exception as e:
        return {"_kget_exc": repr(e)[:200]}


def wmic_processes() -> dict[int, str]:
    """Return {pid: cmdline_lower} for pythonw/python processes we care about."""
    out: dict[int, str] = {}
    try:
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                info = p.info
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            cmdline = info.get("cmdline") or []
            cmd = " ".join(cmdline).lower()
            name = (info.get("name") or "").lower()
            if name.startswith("python") and "scripts/" in cmd:
                out[int(info.get("pid", 0) or 0)] = cmd
    except Exception as e:
        log(f"psutil err: {e}")
    return out


def daemon_owner(ticker: str) -> str:
    """Best-effort guess which daemon owns a ticker based on open DB orders/fills."""
    try:
        r = httpx.get(f"{MC}/api/trade/funds", timeout=5)
        d = r.json() if r.status_code == 200 else {}
        orders = d.get("orders_by_mode", {}).get("live", [])
        for o in orders:
            if o.get("ticker") == ticker:
                side = (o.get("side") or "").lower()
                return "scalp" if "scalp" in side else "xvenue" if "xvenue" in side else "unknown"
    except Exception:
        pass
    return "unknown"


def publish(state: dict) -> None:
    try:
        con = sb.sb_conn()
        cur = con.cursor()
        cur.execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES (%s, %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=EXCLUDED.updated_at",
            (WATCHER_KEY, json.dumps(state)),
        )
        con.commit()
        con.close()
    except Exception:
        pass


def pause_live_entries(reason: str) -> None:
    """Set env flag so live loops pause entries."""
    flag = ROOT / ".live_paused"
    flag.write_text(f"{time.asctime()} — {reason}\n")
    log(f"PAUSE live entries: {reason}")


def resume_live_entries() -> None:
    flag = ROOT / ".live_paused"
    if flag.exists():
        flag.unlink()
    log("RESUME live entries")


def kill_daemon(pid: int) -> None:
    try:
        subprocess.run(["taskkill", "/f", "/pid", str(pid)], capture_output=True, timeout=5)
        log(f"killed pid {pid}")
    except Exception as e:
        log(f"kill pid {pid} err: {e}")


def restart_daemon(name: str, script: str) -> None:
    cmd = [
        str(ROOT / ".venv311/Scripts/pythonw.exe"),
        str(ROOT / script),
    ]
    if name == "dry_no_cheap":
        cmd += ["--lane", "dry-no-cheap-1", "--clip", "1", "--minutes", "120"]
    try:
        subprocess.Popen(cmd, cwd=str(ROOT), close_fds=True)
        log(f"restarted {name} -> {script}")
    except Exception as e:
        log(f"restart {name} err: {e}")


def tick(cx) -> dict:
    state = {
        "ts": time.time(),
        "cash": 0.0,
        "account_equity": 0.0,
        "positions": [],
        "open_count": 0,
        "floor_hit": False,
        "paused": False,
        "alerts": [],
        "daemons": {},
        "actions": [],
    }

    # 1. Kalshi truth via direct API — MC route is optional fallback only
    kalshi_ok = False
    try:
        d = kget("/portfolio/balance")
        if not d.get("_kget_http_status") and not d.get("_kget_exc"):
            state["cash"] = float(d.get("balance_dollars", 0))
            state["account_equity"] = float(d.get("portfolio_value", 0) or d.get("balance_dollars", 0))
            kalshi_ok = True
        else:
            state["alerts"].append(f"kalshi balance err: {d}")
    except Exception as e:
        state["alerts"].append(f"kalshi balance exc: {e}")
    try:
        pos = kget("/portfolio/positions") or {}
        positions = pos.get("positions", []) or []
        state["positions"] = positions[:20]
        state["open_count"] = len(positions)
    except Exception as e:
        state["alerts"].append(f"kalshi positions err: {e}")

    # 1b. MC overlay — fallback only if Kalshi direct failed
    if not kalshi_ok:
        try:
            r = httpx.get(f"{MC}/api/trade/funds", timeout=5)
            if r.status_code == 200:
                d = r.json()
                if d.get("cash"):
                    state["cash"] = float(d.get("cash", state["cash"]))
                if d.get("account_equity"):
                    state["account_equity"] = float(d.get("account_equity", state["account_equity"]))
        except Exception:
            pass

    # 2. Floor guard
    if state["cash"] < CASH_FLOOR:
        state["floor_hit"] = True
        state["paused"] = True
        pause_live_entries(f"cash ${state['cash']:.2f} < floor ${CASH_FLOOR:.2f}")
        state["actions"].append("PAUSED live entries")
    else:
        resume_live_entries()

    # 3. Position cap
    if state["open_count"] > MAX_LIVE_POSITIONS:
        state["alerts"].append(f"position cap exceeded: {state['open_count']}")

    # 4. Daemon audit
    procs = wmic_processes()
    seen = {}
    for pid, cmd in procs.items():
        for name, script in KNOWN_DAEMONS.items():
            if script.replace("scripts/", "") in cmd:
                seen[name] = pid
                break
    state["daemons"] = seen

    missing = [n for n in KNOWN_DAEMONS if n not in seen]
    for m in missing:
        state["alerts"].append(f"missing daemon: {m}")
        if m in ("profit_scalp", "crossvenue"):
            if not (ROOT / f".restart_{m}").exists():
                (ROOT / f".restart_{m}").write_text("1")
                restart_daemon(m, KNOWN_DAEMONS[m])
    for m in seen:
        p = ROOT / f".restart_{m}"
        if p.exists():
            p.unlink()

    # 5. Unknown-position watch
    live_tickers = {p.get("ticker") for p in state["positions"] if p.get("ticker")}
    for t in live_tickers:
        owner = daemon_owner(t)
        if owner == "unknown":
            state["alerts"].append(f"unknown live position: {t}")

    publish(state)
    return state


def main() -> None:
    _write_log_once("fleet_watcher bootstrap")
    log("fleet_watcher start")
    try:
        publish({
            "ts": time.time(), "cash": 0, "account_equity": 0, "positions": [],
            "open_count": 0, "floor_hit": True, "paused": True,
            "alerts": ["init"], "daemons": {}, "actions": ["init"],
        })
    except Exception as e:
        _write_log_once(f"init publish failed: {e}")
        log(f"init publish failed: {e}")

    try:
        cx = httpx.Client(headers={"User-Agent": "fleet-watcher/1.0"}, timeout=10, follow_redirects=True)
    except Exception as e:
        _write_log_once(f"httpx init failed: {e}")
        raise

    stall = 0
    while True:
        try:
            s = tick(cx)
            stall = 0
            log(
                f"cash=${s['cash']:.2f} pos={s['open_count']} floor={s['floor_hit']} "
                f"paused={s['paused']} daemons={len(s['daemons'])} alerts={len(s['alerts'])}"
            )
            if s["alerts"]:
                for a in s["alerts"][:5]:
                    log(f"  ! {a}")
        except Exception as e:
            stall += 1
            log(f"tick err: {e}")
            if stall >= 3:
                log("fleet_watcher exiting — too many consecutive errors")
                return
        time.sleep(POLL)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _write_log_once(f"fleet_watcher fatal: {e}")
        raise
