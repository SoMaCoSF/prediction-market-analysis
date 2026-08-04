# file_id: SOM-PY-1005-v1.0.0 name: bridge_coordinator.py description: Cross-account bridge coordinator — watches Kalshi cash + Polymarket USDC, knows the flow rules between the two venues, and TALKS: publishes bridge:state and raises alerts when a rebalance is warranted. Manual taps are fine; the system stays aware. Zero tokens. project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [bridge, cross-account, funding, polymarket, kalshi, awareness] created: 2026-08-04 version: 1.0.0 agent_id: HERMES-AGENT
"""bridge_coordinator.py — the cross-account funding awareness layer.

The two venues are NOT directly interoperable:
  - Polymarket = USDC on Polygon (withdrawable to any EVM address)
  - Kalshi = USD, NO withdrawal API (manual Venmo tap only)

So "fund each other" means a coordinator that is AWARE of both balances and
TALKS about the allowable flow:
  - Poly surplus + Kalshi low  -> recommend OFF-RAMP Poly -> Kalshi (manual)
  - Kalshi surplus             -> recommend WITHDRAW Kalshi -> Poly (manual)
  - otherwise                  -> BALANCED

It publishes bridge:state (both balances + recommendation + last alert) and
logs an alert on every state change so the human (and any delivery channel)
sees exactly what to do. Manual taps are fine — the system just has to know.
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
POLL_S = 90
USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
RPCS = ["https://1rpc.io/matic", "https://polygon-bor-rpc.publicnode.com"]
POLY_WALLET = "0xbC6662be0803F28C827BC405477F0b5AB8c6Dd40"

# flow thresholds
POLY_SURPLUS = 50.0     # Poly USDC above this, with Kalshi low, is worth moving
KALSHI_LOW = 25.0       # Kalshi cash below this = wants a top-up
KALSHI_SURPLUS = 150.0  # Kalshi cash above this = sweep to Poly


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] [bridge] {m}", flush=True)
    runlog.log_event("bridge", m)


def _sign(method, path, ts):
    from cryptography.hazmat.primitives import hashes, serialization  # noqa
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key((ROOT / ".kalshi_key.pem").read_bytes(), password=None)
    sig = key.sign(f"{ts}{method}{path}".encode(),
                   padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                   hashes.SHA256())
    return base64.b64encode(sig).decode()


def kalshi_cash() -> float:
    try:
        ts = str(int(time.time() * 1000))
        full = "/trade-api/v2/portfolio/balance"
        h = {"KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"),
             "KALSHI-ACCESS-SIGNATURE": _sign("GET", full, ts),
             "KALSHI-ACCESS-TIMESTAMP": ts}
        r = httpx.get(KALSHI + "/portfolio/balance", headers=h, timeout=15)
        j = r.json()
        return float(j.get("balance_dollars") or 0)
    except Exception:
        return -1.0


def poly_usdc(addr: str) -> float:
    data = "0x70a08231" + "0" * 24 + addr[2:].lower()
    for rpc in RPCS:
        try:
            r = httpx.post(rpc, json={"jsonrpc": "2.0", "method": "eth_call",
                           "params": [{"to": USDC, "data": data}, "latest"], "id": 1}, timeout=15)
            j = r.json()
            if "result" in j:
                return int(j["result"], 16) / 1e6
        except Exception:
            continue
    return -1.0


def recommend(kcash: float, pusdc: float) -> tuple[str, str]:
    if pusdc >= POLY_SURPLUS and kcash < KALSHI_LOW:
        return ("OFFRAMP_POLY_TO_KALSHI",
                f"Poly has ${pusdc:.2f} USDC, Kalshi low (${kcash:.2f}). Off-ramp Poly -> deposit to Kalshi (Venmo card).")
    if kcash >= KALSHI_SURPLUS:
        return ("WITHDRAW_KALSHI_TO_POLY",
                f"Kalshi has ${kcash:.2f}. Withdraw to Venmo, then send USDC to Poly wallet {POLY_WALLET[:10]}….")
    return ("BALANCED", "Both venues within ranges. No action.")


def publish(state: dict) -> None:
    try:
        con = sb.sb_conn()
        con.autocommit = True
        cur = con.cursor()
        cur.execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('bridge:state', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (json.dumps(state),))
        con.close()
    except Exception:
        pass


def main():
    fleetlib.acquire_lock("bridge")
    log("bridge start | watching Kalshi cash + Poly USDC | manual taps OK, system stays aware")
    last = None
    while True:
        fleetlib.checkin("bridge")
        try:
            kcash = kalshi_cash()
            pusdc = poly_usdc(POLY_WALLET)
            rec, msg = recommend(kcash, pusdc)
            state = {"kalshi_cash": round(kcash, 2), "poly_usdc": round(pusdc, 2),
                     "recommendation": rec, "message": msg, "ts": int(time.time())}
            publish(state)
            if rec != last:
                if rec != "BALANCED":
                    log(f"BRIDGE ALERT: {rec} — {msg}")
                else:
                    log(f"bridge balanced (was {last})")
                last = rec
            else:
                log(f"state {rec} | Kalshi ${kcash:.2f} / Poly ${pusdc:.2f}")
        except Exception as e:
            log(f"warn {repr(e)[:60]}")
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
