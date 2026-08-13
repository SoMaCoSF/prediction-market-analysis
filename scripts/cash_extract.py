#!/usr/bin/env python3
"""Extract Kalshi live balance to a local file."""
import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from kalshi_python.api_client import ApiClient
from kalshi_python.api.portfolio_api import PortfolioApi

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "kalshi_balance.json"


def main():
    client = ApiClient()
    client.set_kalshi_auth(os.environ["KALSHI_KEY_ID"], str(ROOT / ".kalshi_key.pem"))
    api = PortfolioApi(client)
    bal = api.get_balance()
    pos = api.get_positions()

    balance = getattr(bal, "balance", None)
    if balance is None:
        balance = 0.0
    balance = float(balance) / 100.0

    positions_raw = getattr(pos, "positions", None)
    positions = []
    if positions_raw is not None:
        for p in positions_raw:
            positions.append({
                "ticker": getattr(p, "ticker", None),
                "side": getattr(p, "side", None),
                "count": getattr(p, "count", None),
                "avg_price": getattr(p, "avg_price", None),
                "current_price": getattr(p, "current_price", None),
                "value": getattr(p, "value", None),
                "pnl": getattr(p, "pnl", None),
            })

    out = {
        "balance": balance,
        "positions_count": len(positions),
        "positions": positions,
        "source": "kalshi_python SDK verified",
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
