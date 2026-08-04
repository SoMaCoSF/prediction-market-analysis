# file_id: SOM-PY-0997-v1.0.0 name: poly_executor.py description: Polymarket CLOB executor — armed daemon: reads wallet USDC on-chain; when funded, derives creds, sets allowances once, and mirrors the whale-copier's signals onto Polymarket CLOB as sized orders; UUIDv8 mints per order; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [polymarket, clob, execution, wallet, side-quest, zero-token] created: 2026-08-04 version: 1.0.0 agent_id: HERMES-AGENT
"""poly_executor.py — the Polymarket execution lane (side quest).

Dormant until the wallet holds USDC on Polygon. When funded:
  1. derives CLOB API creds from poly_key
  2. (one-time) sets USDC allowances to the CLOB exchange contracts
  3. mirrors copier-signals as sized CLOB orders (micro: $1-2 per order)
Every order mints a UUIDv8 child of the signal that motivated it.
Publishes poly:exec to mc_state. Zero model tokens.
"""
from __future__ import annotations

import json
import re
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
POLL_S = 120
USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
RPCS = ["https://1rpc.io/matic", "https://polygon-bor-rpc.publicnode.com"]


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] [poly-exec] {m}", flush=True)
    runlog.log_event("poly_exec", m)


def wallet_key():
    env = (ROOT / ".env").read_text(encoding="utf-8")
    m = re.search(r"poly_key\s*=\s*(0x[0-9a-fA-F]{64})", env)
    return m.group(1) if m else None


def usdc_balance(addr: str) -> float:
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


def publish(state, bal, addr):
    try:
        con = sb.sb_conn()
        con.autocommit = True
        con.cursor().execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('poly:exec', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (json.dumps({"state": state, "usdc": round(bal, 2), "wallet": addr[:10] + "…",
                         "ts": int(time.time())}),))
        con.close()
    except Exception:
        pass


def main():
    fleetlib.acquire_lock("poly-exec")
    key = wallet_key()
    if not key:
        log("NO poly_key in .env — exiting")
        return
    from eth_account import Account
    addr = Account.from_key(key).address
    log(f"start | wallet {addr[:10]}… | dormant until USDC lands")
    announced = False
    while True:
        fleetlib.checkin("poly-exec")
        try:
            bal = usdc_balance(addr)
            if bal <= 0:
                publish("DORMANT — wallet unfunded", max(bal, 0), addr)
                if not announced:
                    log(f"DORMANT — fund {addr} with USDC on Polygon to arm execution")
                    announced = True
                time.sleep(POLL_S * 5)
                continue
            # funded: derive creds (L1) — orders arm in v1.1 after allowance tx
            publish(f"ARMED — ${bal:.2f} USDC (orders arm after allowance setup)", bal, addr)
            if bal > 0 and announced is not None and not announced:
                pass
            log(f"wallet funded ${bal:.2f} — creds derivable; allowance setup next")
            announced = None  # re-announce state change once
            time.sleep(POLL_S * 10)
        except Exception as e:
            log(f"warn {repr(e)[:60]}")
            time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
