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
kalshi_cash: float | None = None


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


def kalshi_cash() -> float:
    """Kalshi-side deposit detection: cash delta = a reload landing."""
    try:
        from run_report import kget
        b = kget("/portfolio/balance")
        return float(b.get("balance_dollars") or 0)
    except Exception:
        return -1.0


def kalshi_cash() -> float:
    try:
        from run_report import kget
        b = kget("/portfolio/balance")
        return float(b.get("balance_dollars") or 0)
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
    log("start | watching wallets for inbound slurps + Kalshi cash deltas")
    feed: list[dict] = []
    last_kalshi_cash = None
    while True:
        try:
            fleetlib.checkin("funding")
            # Kalshi-side reload detection (exchange cash rising = deposit landed)
            try:
                from run_report import kget
                b = kget("/portfolio/balance")
                kc = float(b.get("balance_dollars") or 0)
                if last_kalshi_cash is not None and kc > last_kalshi_cash + 1.0:
                    delta = kc - last_kalshi_cash
                    u = mint_funding("kalshi-reload", "exchange", delta)
                    feed.append({"label": "kalshi-reload", "chain": "exchange", "delta": round(delta, 2),
                                 "balance": round(kc, 2), "uuid": u, "ts": int(time.time())})
                    log(f"RELOAD DETECTED +${delta:.2f} -> cash ${kc:.2f} | ladder stepping up")
                last_kalshi_cash = kc
            except Exception:
                pass
            # Kalshi-side: a cash jump = a deposit landed
            try:
                from run_report import kget
                kb = kget('/portfolio/balance')
                kcash = float(kb.get('balance_dollars') or 0)
                if 'kalshi' in balances and kcash > balances['kalshi'] + 0.50:
                    delta = kcash - balances['kalshi']
                    u = mint_funding('kalshi-deposit', 'kalshi', delta)
                    feed.append({'label': 'kalshi-deposit', 'chain': 'kalshi', 'delta': round(delta, 2),
                                 'balance': round(kcash, 2), 'uuid': u, 'ts': int(time.time())})
                    log(f'RELOAD DETECTED Kalshi +${delta:.2f} -> ${kcash:.2f}')
                balances['kalshi'] = kcash
            except Exception:
                pass
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
            # Kalshi-side: a cash jump with no fills = a deposit landing (the reload)
            global kalshi_cash
            try:
                from run_report import kget
                b = kget("/portfolio/balance")
                cash_now = float(b.get("balance_dollars") or 0)
                if kalshi_cash is not None and cash_now > kalshi_cash + 5.0:
                    delta = cash_now - kalshi_cash
                    u = mint_funding("kalshi-deposit", "kalshi", delta)
                    feed.append({"label": "kalshi-deposit", "chain": "kalshi", "delta": round(delta, 2),
                                 "balance": round(cash_now, 2), "uuid": u, "ts": int(time.time())})
                    log(f"RELOAD DETECTED +${delta:.2f} -> cash ${cash_now:.2f} — the ladder steps up")
                    publish(feed)
                kalshi_cash = cash_now
            except Exception:
                pass
            # Kalshi-side deposit detection: cash rising with no engine spend context = a reload
            kc = kalshi_cash()
            if kc >= 0:
                if "kalshi" in balances and kc > balances["kalshi"] + 5.0:
                    delta = kc - balances["kalshi"]
                    u = mint_funding("kalshi-deposit", "kalshi", delta)
                    feed.append({"label": "kalshi-deposit", "chain": "kalshi", "delta": round(delta, 2),
                                 "balance": round(kc, 2), "uuid": u, "ts": int(time.time())})
                    log(f"RELOAD DETECTED +${delta:.2f} -> Kalshi cash ${kc:.2f} — ladder steps up")
                balances["kalshi"] = kc
        except Exception as e:
            log(f"warn {repr(e)[:60]}")
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
