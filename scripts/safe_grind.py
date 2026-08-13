"""Minimal Kalshi micro-grinder using the official SDK only."""
import json
import os
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from kalshi_python.api.markets_api import MarketsApi
from kalshi_python.api.portfolio_api import PortfolioApi
from kalshi_python.api_client import ApiClient
from kalshi_python.models.create_order_request import CreateOrderRequest

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "data" / "wti_watch_state.json"
RESERVE_FLOOR = 2.00
MAX_ORDER_NOTIONAL = 5.00
MAX_ORDER_COUNT = 5


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"balance": 0, "positions": 0, "trades": 0}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def get_client():
    client = ApiClient()
    client.set_kalshi_auth(os.environ["KALSHI_KEY_ID"], str(ROOT / ".kalshi_key.pem"))
    return client


def get_balance(client):
    api = PortfolioApi(client)
    resp = api.get_balance()
    balance = getattr(resp, "balance", None)
    if balance is None:
        return 0.0
    return float(balance)


def find_opportunity(client):
    """Scan for any market with executable depth."""
    markets_api = MarketsApi(client)
    try:
        resp = markets_api.get_markets(limit=200, status="open")
        markets = resp.markets if hasattr(resp, "markets") else []
    except Exception as e:
        print(f"Market scan error: {e}")
        return None

    for m in markets:
        yes_ask = getattr(m, "yes_ask_dollars", None)
        no_ask = getattr(m, "no_ask_dollars", None)
        vol = getattr(m, "volume_24h", None) or getattr(m, "volume", None) or 0

        if vol <= 0:
            continue
        if yes_ask is None and no_ask is None:
            continue

        # Prefer cheap YES
        if yes_ask is not None and yes_ask <= 0.15:
            return {
                "ticker": m.ticker,
                "side": "yes",
                "price": float(yes_ask),
                "reason": f"YES ask {yes_ask} <= 15¢, vol={vol}",
            }
        # Fallback: cheap NO implies expensive YES
        if no_ask is not None and no_ask >= 0.85:
            yes_effective = 1.0 - float(no_ask)
            if yes_effective <= 0.15:
                return {
                    "ticker": m.ticker,
                    "side": "yes",
                    "price": yes_effective,
                    "reason": f"NO ask {no_ask} => YES ~{yes_effective:.2f}, vol={vol}",
                }
    return None


def place_order(client, ticker, side, price, count=1):
    """Place a limit order using SDK."""
    api = PortfolioApi(client)
    price_cents = int(round(price * 100))
    order = CreateOrderRequest(
        ticker=ticker,
        action="buy",
        side=side,
        count=count,
        type="limit",
        yes_price=price_cents if side == "yes" else None,
        no_price=price_cents if side == "no" else None,
        client_order_id=f"grind-{int(time.time())}",
    )
    try:
        resp = api.create_order(order)
        print(f"Order placed: {ticker} {side} x{count} @ {price}")
        print(f"Response: {resp}")
        return True
    except Exception as e:
        print(f"Order failed: {e}")
        return False


def main():
    state = load_state()
    client = get_client()

    # Update balance
    balance = get_balance(client)
    print(f"Live balance: ${balance:.2f}")
    state["balance"] = balance

    if balance <= RESERVE_FLOOR:
        print(f"At floor ${RESERVE_FLOOR}. No trades.")
        save_state(state)
        return

    # Find opportunity
    opp = find_opportunity(client)
    if not opp:
        print("No opportunity found. Sleeping.")
        save_state(state)
        return

    print(f"Found: {opp['ticker']} {opp['side']} @ {opp['price']} ({opp['reason']})")

    # Check notional
    notional = float(opp["price"]) * 1
    available = balance - RESERVE_FLOOR
    if notional > min(MAX_ORDER_NOTIONAL, available):
        print(f"Notional ${notional:.2f} exceeds limit. Skipping.")
        save_state(state)
        return

    # Place order
    success = place_order(client, opp["ticker"], opp["side"], opp["price"], count=1)
    if success:
        state["trades"] = state.get("trades", 0) + 1
        state["positions"] = state.get("positions", 0) + 1

    save_state(state)
    print("Done.")


if __name__ == "__main__":
    main()
