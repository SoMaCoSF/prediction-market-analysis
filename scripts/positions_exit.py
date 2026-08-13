"""Exit Kalshi positions at best executable ask price."""
import json
import os
import time
import uuid
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
KEY_PATH = ROOT / ".kalshi_key.pem"
BASE = "https://external-api.kalshi.com/trade-api/v2"


def signed_request(method: str, path: str, body: dict | None = None, params: dict | None = None):
    key_pem = KEY_PATH.read_text()
    private_key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    ts = str(int(time.time() * 1000))
    msg = f"{ts}{method.upper()}/trade-api/v2{path}".encode()
    sig = private_key.sign(
        msg,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    headers = {
        "KALSHI-ACCESS-KEY": os.environ["KALSHI_KEY_ID"],
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": __import__("base64").b64encode(sig).decode(),
        "Content-Type": "application/json",
    }
    url = f"{BASE}{path}"
    if method.upper() == "POST":
        return httpx.post(url, headers=headers, json=body, timeout=20)
    return httpx.get(url, headers=headers, params=params, timeout=20)


def main():
    # Load positions from cash extract
    bal_path = ROOT / "data" / "kalshi_balance.json"
    data = json.loads(bal_path.read_text())
    positions = data.get("positions", [])
    print(f"Loaded {len(positions)} positions")

    closed = 0
    for p in positions:
        ticker = p.get("ticker")
        count = float(p.get("count") or 0)
        value = float(p.get("value") or 0)
        if not ticker or count <= 0:
            continue

        # Priority: close zero-value positions first
        if value > 0.5:
            print(f"SKIP {ticker}: value={value} > 0.5, keep exposure")
            continue

        # Check orderbook for best ask
        ob_resp = signed_request("GET", f"/markets/{ticker}/orderbook")
        if ob_resp.status_code != 200:
            print(f"SKIP {ticker}: orderbook {ob_resp.status_code}")
            continue

        ob = ob_resp.json().get("orderbook_fp", {})

        # Find best bid price for immediate exit
        best_price = None
        side = None
        if ob.get("yes_dollars"):
            best_price = ob["yes_dollars"][0][0]
            side = "ask"
        elif ob.get("no_dollars"):
            best_price = ob["no_dollars"][0][0]
            side = "bid"
        else:
            print(f"SKIP {ticker}: empty orderbook")
            continue

        if not best_price or not side:
            print(f"SKIP {ticker}: no asks in book")
            continue

        # Place exit order: sell 1 share at best ask with 4-decimal format
        price = f"{float(best_price):.4f}"

        body = {
            "ticker": ticker,
            "client_order_id": f"exit-{uuid.uuid4().hex[:8]}",
            "side": side,
            "count": "1.00",
            "price": price,
            "time_in_force": "immediate_or_cancel",
            "self_trade_prevention_type": "taker_at_cross",
            "post_only": False,
            "cancel_order_on_pause": False,
            "reduce_only": True,
            "subaccount": 0,
            "exchange_index": 0,
        }

        r = signed_request("POST", "/portfolio/events/orders", body)
        print(f"EXIT {ticker} x1 @ {price}: {r.status_code} {r.text[:200]}")
        if r.status_code == 201:
            closed += 1
        time.sleep(0.3)

    print(f"Closed {closed} positions")


if __name__ == "__main__":
    main()
