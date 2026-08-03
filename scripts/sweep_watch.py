# file_id: SOM-PY-0961-v1.0.0 name: sweep_watch.py description: Venmo sweep watcher — alerts when Kalshi cash >= TRIGGER ($140) to sweep $40 to Venmo; tracks sweep state + history in mc_state; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [sweep, venmo, cashout, watcher, alerts] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""sweep_watch.py — the cashout ritual, automated except the 30-second tap.

Kalshi has no withdrawal API. So: watch cash every 60s. When cash >= $140,
raise a pending-sweep alert (mc_log kind='alert' + mc_state sweep:pending)
telling the user to sweep $40 to Venmo in the Kalshi app. When cash drops
>= $30 below the trigger peak (user swept), record the sweep: count, total,
history in mc_state sweep:stats. Panel reads the state and shows the banner.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import httpx  # noqa: E402
import runlog  # noqa: E402
import sb  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
TRIGGER = 200.00
SWEEP = 100.00
POLL_S = 60


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
        return r.json() if "json" in r.headers.get("content-type", "") else {}
    except Exception:
        return {}


def cash():
    return float(kget("/portfolio/balance").get("balance_dollars") or 0)


def mc_put(k, v):
    con = sb.sb_conn()
    con.autocommit = True
    con.cursor().execute(
        "INSERT INTO mc_state (k, v, updated_at) VALUES (%s, %s, now()) "
        "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()", (k, v))
    con.close()


def mc_get(k):
    try:
        con = sb.sb_conn()
        cur = con.cursor()
        cur.execute("SELECT v FROM mc_state WHERE k=%s", (k,))
        r = cur.fetchone()
        con.close()
        return r[0] if r else None
    except Exception:
        return None


def mc_alert(msg):
    try:
        con = sb.sb_conn()
        con.autocommit = True
        con.cursor().execute("INSERT INTO mc_log (ts, kind, msg) VALUES (%s, 'alert', %s)", (int(time.time()), msg))
        con.close()
    except Exception:
        pass


def stats():
    try:
        return json.loads(mc_get("sweep:stats") or "{}")
    except Exception:
        return {}


def main():
    fleetlib.acquire_lock("sweep")
    runlog.log_event("sweep", f"sweep watch start trigger=${TRIGGER} sweep=${SWEEP}")
    print(f"[sweep] watching: cash >= ${TRIGGER:.0f} -> alert to sweep ${SWEEP:.0f} to Venmo", flush=True)
    pending_since = None
    pending_pv = 0.0
    peak = 0.0
    while True:
        fleetlib.checkin("sweep")
        try:
            c = cash()
            if not c:
                time.sleep(POLL_S)
                continue
            s = stats()
            if pending_since is None and c >= TRIGGER:
                pending_since = time.time()
                peak = c
                pending_pv = (kget("/portfolio/balance").get("portfolio_value") or 0) / 100
                mc_put("sweep:pending", json.dumps({"since": pending_since, "peak": c, "amount": SWEEP}))
                msg = f"SWEEP TIME: cash ${c:.2f} >= ${TRIGGER:.0f} — withdraw ${SWEEP:.0f} to Venmo in the Kalshi app (30s tap)"
                mc_alert(msg)
                runlog.log_event("sweep", msg, kind="alert")
                print(f"[sweep] {msg}", flush=True)
            elif pending_since is not None:
                peak = max(peak, c)
                # real sweep = cash down >=80% of SWEEP while positions didn't grow
                bal = kget("/portfolio/balance")
                pv_now = (bal.get("portfolio_value") or 0) / 100
                if c <= peak - SWEEP * 0.8 and pv_now <= pending_pv + 20:
                    st = stats()
                    st["count"] = int(st.get("count", 0)) + 1
                    st["total"] = float(st.get("total", 0)) + SWEEP
                    st["last_ts"] = int(time.time())
                    mc_put("sweep:stats", json.dumps(st))
                    mc_put("sweep:pending", "")
                    msg2 = f"sweep #{st['count']} CONFIRMED (${SWEEP:.0f} -> Venmo) | lifetime swept ${st['total']:.0f}"
                    mc_alert(msg2)
                    runlog.log_event("sweep", msg2)
                    print(f"[sweep] {msg2}", flush=True)
                    pending_since = None
                    peak = 0.0
        except Exception as e:
            runlog.log_event("sweep", f"warn {repr(e)[:60]}", kind="warn")
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
