#!/usr/bin/env python3
"""Self-contained invest API data provider."""
import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

BASE = "https://external-api.kalshi.com/trade-api/v2"
KEY_PATH = Path(__file__).resolve().parent.parent / ".kalshi_key.pem"


def signed_get(path: str) -> dict:
    key_pem = KEY_PATH.read_text()
    private_key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    ts = str(int(Path(__file__).stat().st_mtime * 1000))
    msg = f"{ts}GET/trade-api/v2{path}".encode()
    sig = private_key.sign(
        msg,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    headers = {
        "KALSHI-ACCESS-KEY": os.environ["KALSHI_KEY_ID"],
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": __import__("base64").b64encode(sig).decode(),
    }
    r = httpx.get(f"{BASE}{path}", headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()


def main():
    bal = signed_get("/portfolio/balance")
    balance = float(bal.get("balance_dollars") or bal.get("balance") or 0)

    pos = signed_get("/portfolio/positions?limit=200")
    raw = pos.get("event_positions", [])
    positions = []
    for p in raw:
        shares = float(p.get("total_cost_shares_fp") or 0)
        avg = float(p.get("avg_price") or 0)
        current = float(p.get("current_price") or avg or 0)
        value = shares * current
        pnl = float(p.get("total_profit") or 0)
        positions.append({
            "ticker": p.get("event_ticker") or p.get("ticker") or "UNKNOWN",
            "side": (p.get("side") or "yes").lower(),
            "count": shares,
            "value": value,
            "pnl": pnl,
            "avg_price": avg,
            "current_price": current,
        })

    win_count = sum(1 for p in positions if (p["pnl"] or 0) > 0)
    loss_count = sum(1 for p in positions if (p["pnl"] or 0) < 0)
    win_rate = int(win_count / len(positions) * 100) if positions else 0
    avg_win = sum(p["pnl"] for p in positions if p["pnl"] > 0) / win_count if win_count else 0
    avg_loss = abs(sum(p["pnl"] for p in positions if p["pnl"] < 0) / loss_count) if loss_count else 0
    profit_factor = (win_count * avg_win) / (loss_count * avg_loss) if avg_loss > 0 else (999 if win_count else 0)
    total_pnl = sum(p["pnl"] for p in positions)
    total_value = sum(p["value"] for p in positions)

    print(json.dumps({
        "balance": balance,
        "positions": positions,
        "stats": {
            "balance": balance,
            "total_value": round(total_value, 2),
            "total_pnl": round(total_pnl, 2),
            "positions_count": len(positions),
            "win_rate": win_rate,
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "total_trades": 0,
        },
        "generated_at": __import__("datetime").datetime.now().isoformat(),
    }))


if __name__ == "__main__":
    main()
