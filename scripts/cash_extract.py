#!/usr/bin/env python3
"""Extract Kalshi live balance to a local file."""
import json
import os
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "kalshi_balance.json"


def main():
    key_pem = (ROOT / ".kalshi_key.pem").read_text()
    private_key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    def signed_get(path, params=None):
        ts = str(int(time.time() * 1000))
        msg = f"{ts}GET/trade-api/v2{path}".encode()
        sig = private_key.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
        h = {
            "KALSHI-ACCESS-KEY": os.environ["KALSHI_KEY_ID"],
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": __import__("base64").b64encode(sig).decode(),
        }
        return httpx.get("https://external-api.kalshi.com/trade-api/v2" + path, headers=h, params=params, timeout=20)

    bal = signed_get("/portfolio/balance").json()
    pos = signed_get("/portfolio/positions", {"limit": "200"}).json()

    raw_balance = bal.get("balance_dollars") or bal.get("balance") or 0
    balance = float(raw_balance)
    if balance > 100:
        balance = balance / 100.0

    positions_raw = pos.get("event_positions") or pos.get("positions") or []
    positions = []
    for p in positions_raw:
        positions.append({
            "ticker": p.get("event_ticker") or p.get("ticker"),
            "side": p.get("side"),
            "count": float(p.get("total_cost_shares_fp") or p.get("count") or 0),
            "avg_price": p.get("avg_price"),
            "current_price": p.get("current_price"),
            "value": float(p.get("event_exposure_dollars") or p.get("value") or 0),
            "pnl": float(p.get("realized_pnl_dollars") or p.get("pnl") or 0),
        })

    out = {
        "balance": balance,
        "positions_count": len(positions),
        "positions": positions,
        "source": "direct Kalshi V2",
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
