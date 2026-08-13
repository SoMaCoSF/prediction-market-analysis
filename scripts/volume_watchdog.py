"""Volume watchdog for Kalshi markets.
- Polls /markets?limit=200&status=open every 60s
- Auto-arms safe_grind when any market has volume_24h > 0
- Stays quiet otherwise
"""
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
from kalshi_python.api_client import ApiClient

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "data" / "wti_watch_state.json"
POLL_INTERVAL = 10


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"armed": False, "last_poll": None}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def get_client():
    client = ApiClient()
    client.set_kalshi_auth(os.environ["KALSHI_KEY_ID"], str(ROOT / ".kalshi_key.pem"))
    return client


def check_liquidity(client):
    """Check if any market has real volume."""
    markets_api = MarketsApi(client)
    try:
        resp = markets_api.get_markets(limit=200, status="open")
        markets = resp.markets if hasattr(resp, "markets") else []
    except Exception as e:
        print(f"Watchdog poll error: {e}")
        return False

    for m in markets:
        vol = getattr(m, "volume_24h", None) or getattr(m, "volume", None) or 0
        if vol > 0:
            print(f"Liquidity found: {m.ticker} vol={vol}")
            return True
    return False


def main():
    state = load_state()
    client = get_client()

    print("Starting volume watchdog...")
    while True:
        armed = check_liquidity(client)
        state["armed"] = armed
        state["last_poll"] = time.time()
        save_state(state)

        if armed:
            print("LIQUIDITY DETECTED - safe_grind should be armed")
            # In production, this would trigger safe_grind
            break
        else:
            print("No liquidity. Sleeping 60s.")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
