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
MC = os.getenv("MC_URL", "http://127.0.0.1:8420")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
PK = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()

WALLETS_JSON = ROOT / "data" / "wallets.json"
POLL_S = 90
RPCS = {"polygon": ["https://1rpc.io/matic", "https://polygon-bor-rpc.publicnode.com"],
        "base": ["https://mainnet.base.org", "https://1rpc.io/base"]}
USDC = {"polygon": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"}
TYPE_FUNDING = 0x3D6

balances: dict[str, float] = {}
last_kalshi_cash: float | None = None


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


def kget(path):
    """Local Kalshi auth — same signing as profit_scalp/run_report."""
    try:
        import base64 as _b64

        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        ts = str(int(time.time() * 1000))
        full = "/trade-api/v2" + path.split("?")[0]
        key = serialization.load_pem_private_key((ROOT / ".kalshi_key.pem").read_bytes(), password=None)
        sig = key.sign(f"{ts}GET{full}".encode(),
                       padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                       hashes.SHA256())
        h = {"KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"),
             "KALSHI-ACCESS-SIGNATURE": _b64.b64encode(sig).decode(),
             "KALSHI-ACCESS-TIMESTAMP": ts}
        r = httpx.get(KALSHI + path, headers=h, timeout=15)
        return r.json() if "json" in r.headers.get("content-type", "") else {}
    except Exception:
        return {}


def kalshi_cash() -> float:
    try:
        return float(kget("/portfolio/balance").get("balance_dollars") or 0)
    except Exception:
        return -1.0


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
        u = uuid_ledger.mint(TYPE_FUNDING, content, provenance=0xE)
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
    global last_kalshi_cash
    fleetlib.acquire_lock("funding")
    log("start | watching wallets for inbound slurps + Kalshi cash deltas")
    feed: list[dict] = []

    while True:
        try:
            fleetlib.checkin("funding")

            # ---- Kalshi balance delta (single check per cycle) ----
            try:
                kc = kalshi_cash()
                if kc >= 0:
                    if last_kalshi_cash is not None and kc > last_kalshi_cash + 0.50:
                        delta = kc - last_kalshi_cash
                        u = mint_funding("kalshi-deposit", "kalshi", delta)
                        feed.append({"label": "kalshi-deposit", "chain": "kalshi",
                                     "delta": round(delta, 2), "balance": round(kc, 2),
                                     "uuid": u, "ts": int(time.time())})
                        log(f"RELOAD DETECTED +${delta:.2f} -> Kalshi cash ${kc:.2f}")
                    last_kalshi_cash = kc
            except Exception:
                pass

            # ---- Wallet USDC slurp detection ----
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
