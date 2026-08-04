# file_id: SOM-PY-0998-v1.0.0 name: funding_feed.py description: Self-funding feed — watches configured wallets (Polygon/Base) for inbound USDC slurps via balance-delta detection; every slurp mints a 0x3D6 FUNDING UUIDv8 event and publishes fund:feed; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [funding, wallets, slurp, usdc, ledger, zero-token] created: 2026-08-04 version: 1.0.0 agent_id: HERMES-AGENT
"""funding_feed.py — the self-funding watcher.

Wallets listed in data/wallets.json are polled on public RPCs. A rising
USDC balance = an inbound slurp: minted as a 0x3D6 FUNDING event in the
ledger and published to fund:feed for the surfaces. Kalshi-side deposits
are detected the same way (balance delta on the exchange balance).
Zero model tokens.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import httpx  # noqa: E402
import runlog  # noqa: E402
import sb  # noqa: E402

WALLETS_JSON = ROOT / "data" / "wallets.json"
POLL_S = 90
RPCS = {"polygon": ["https://1rpc.io/matic", "https://polygon-bor-rpc.publicnode.com"],
        "base": ["https://mainnet.base.org", "https://1rpc.io/base"]}
USDC = {"polygon": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"}
TYPE_FUNDING = 0x3D6

balances: dict[str, float] = {}


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] [funding] {m}", flush=True)
    runlog.log_event("funding", m)


def load_wallets():
    if WALLETS_JSON.exists():
        try:
            return json.loads(WALLETS_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def usdc_balance(chain: str, addr: str) -> float:
    data = "0x70a08231" + "0" * 24 + addr[2:].lower()
    for rpc in RPCS.get(chain, []):
        try:
            r = httpx.post(rpc, json={"jsonrpc": "2.0", "method": "eth_call",
                           "params": [{"to": USDC[chain], "data": data}, "latest"], "id": 1}, timeout=15)
            j = r.json()
            if "result" in j:
                return int(j["result"], 16) / 1e6
        except Exception:
            continue
    return -1.0


def mint_funding(label: str, chain: str, delta: float):
    """0x3D6 FUNDING event into the ledger."""
    try:
        import uuid_ledger
        content = hashlib.sha256(f"funding|{label}|{chain}|{delta:.6f}|{int(time.time())}".encode()).digest()
        u = uuid_ledger.mint(TYPE_FUNDING, content, provenance=0xE)  # 0xE = external capital
        uuid_ledger.store(u, f"FUNDING {label} {chain} +${delta:.2f}")
        return u
    except Exception:
        return None


def publish(feed):
    try:
        con = sb.sb_conn()
        con.autocommit = True
        con.cursor().execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('fund:feed', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (json.dumps(feed[-20:]),))
        con.close()
    except Exception:
        pass


def main():
    fleetlib.acquire_lock("funding")
    log("start | watching wallets for inbound slurps")
    feed: list[dict] = []
    while True:
        try:
            fleetlib.checkin("funding")
            for w in load_wallets():
                label, chain, addr = w.get("label", "?"), w.get("chain", "polygon"), w.get("address", "")
                if not addr:
                    continue
                key = f"{chain}:{addr}"
                bal = usdc_balance(chain, addr)
                if bal < 0:
                    continue
                if key in balances and bal > balances[key] + 0.005:
                    delta = bal - balances[key]
                    u = mint_funding(label, chain, delta)
                    feed.append({"label": label, "chain": chain, "delta": round(delta, 2),
                                 "balance": round(bal, 2), "uuid": u, "ts": int(time.time())})
                    log(f"SLURP {label} ({chain}) +${delta:.2f} -> ${bal:.2f} | uuid {str(u)[:18] if u else '—'}")
                balances[key] = bal
            publish(feed)
        except Exception as e:
            log(f"warn {repr(e)[:60]}")
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
