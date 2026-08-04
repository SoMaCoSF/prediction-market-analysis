# file_id: SOM-PY-0985-v1.0.0 name: vault.py description: Bankroll vault daemon — every 60s reads Kalshi balance (RSA-PSS signed GET /portfolio/balance), locks a reserve = min($100, 50% of equity), computes trading allowance = max(0, cash - reserve), publishes mc_state vault:state so every engine's cash floor follows equity project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [vault, bankroll, reserve, risk, fleet, zero-token] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""vault.py — the bankroll vault.

One locked reserve, one spendable allowance, published for the whole fleet:
  reserve   = min(50, equity * 0.30)  # never trade below this line (30% — 50% strangled entries at small equity)
  allowance = max(0, cash - reserve)   # what engines may actually put at risk
  equity    = cash + portfolio_value

Engines (trend_engine, profit_scalp) read mc_state 'vault:state' reserve as
their cash floor, falling back to the hardcoded $20 when vault state is
missing or stale (>300s). Zero model tokens: signed REST read + one upsert.
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
POLL = 60
RESERVE_CAP = 100.0     # reserve never exceeds $100
RESERVE_FRAC = 0.30     # 30% reserve at small bankrolls (your rule); 50% strangles entries to $0
FLOOR_MIN = 0.50        # cash floor never exceeds this — sub-$1 bankrolls can still grind


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] [vault] {m}", flush=True)
    runlog.log_event("vault", m)


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


def snapshot() -> dict | None:
    """Exchange truth -> vault state. None when the balance read failed."""
    bal = kget("/portfolio/balance")
    if not bal or "balance_dollars" not in bal:
        return None
    cash = float(bal.get("balance_dollars") or 0)
    pv = (bal.get("portfolio_value") or 0) / 100
    equity = cash + pv
    reserve = min(RESERVE_CAP, equity * RESERVE_FRAC)
    floor = min(FLOOR_MIN, reserve)   # engine cash floor — never blocks sub-$1 grind
    allowance = max(0.0, cash - reserve)
    return {"reserve": round(reserve, 2), "allowance": round(allowance, 2),
            "floor": round(floor, 2), "equity": round(equity, 2), "ts": time.time()}


def publish(state: dict) -> None:
    con = sb.sb_conn()
    con.autocommit = True
    cur = con.cursor()
    cur.execute(
        "INSERT INTO mc_state (k, v, updated_at) VALUES ('vault:state', %s, now()) "
        "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
        (json.dumps(state),))
    con.close()


def main():
    fleetlib.acquire_lock("vault")
    log(f"vault start | reserve=min(${RESERVE_CAP:.0f}, equity*{RESERVE_FRAC}) poll={POLL}s")
    while True:
        fleetlib.checkin("vault")
        try:
            state = snapshot()
            if state is None:
                log("balance read failed — keeping last published state")
            else:
                publish(state)
                runlog.assert_event(
                    0 <= state["reserve"] <= RESERVE_CAP and state["allowance"] >= 0,
                    "vault", "reserve within [0, cap] and allowance non-negative",
                    reserve=state["reserve"], allowance=state["allowance"], equity=state["equity"])
                log(f"equity ${state['equity']:.2f} | reserve ${state['reserve']:.2f} locked | "
                    f"allowance ${state['allowance']:.2f}")
        except Exception as e:
            log(f"cycle warn {repr(e)[:60]}")
        time.sleep(POLL)


if __name__ == "__main__":
    sys.exit(main())
