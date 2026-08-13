"""Conservative Kalshi micro-grinder with real liquidity check.
Safety rules:
- Hard floor at $2.00 cash
- Only trades markets with volume_24h > 0 and real orderbook depth
- Small position sizes
- Uses mission_control.py signing logic
"""
import os
import time
import json
import math
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# Config
FLOOR = 2.00
MAX_POSITION_SIZE = 0.50  # max $ per trade
MAX_POSITIONS = 10
MIN_LIQUIDITY = 100  # minimum volume_24h
STATE_FILE = Path("data/grind_state.json")

# Paths
KEY_ID = os.environ["KALSHI_KEY_ID"]
KEY_PATH = ".kalshi_key.pem"

from kalshi_python.api_client import ApiClient
from kalshi_python.api.portfolio_api import PortfolioApi
from kalshi_python.api.markets_api import MarketsApi

client = ApiClient()
client.set_kalshi_auth(KEY_ID, KEY_PATH)
portfolio_api = PortfolioApi(client)
markets_api = MarketsApi(client)


def get_balance():
    bal = portfolio_api.get_balance()
    return float(getattr(bal, "balance", 0))


def get_positions():
    try:
        p = portfolio_api.get_positions()
        data = p.model_dump() if hasattr(p, "model_dump") else getattr(p, "dict", lambda: None)()
        return data.get("positions") or []
    except Exception as e:
        print(f"[WARN] get_positions failed: {e}")
        return []


def get_open_markets(limit=200):
    resp = markets_api.get_markets(limit=limit, status="open")
    data = resp.model_dump() if hasattr(resp, "model_dump") else getattr(resp, "dict", lambda: {})()
    return data.get("markets", [])


def check_orderbook_depth(ticker):
    """Check if orderbook has real depth. Returns True if viable."""
    try:
        ob = markets_api.get_orderbook(ticker)
        ob_data = ob.model_dump() if hasattr(ob, "model_dump") else getattr(ob, "dict", lambda: {})()
        yes = ob_data.get("yes", {})
        no = ob_data.get("no", {})
        
        yes_bid = yes.get("bid", 0)
        yes_ask = yes.get("ask", 100)
        no_bid = no.get("bid", 0)
        no_ask = no.get("ask", 100)
        
        # Check spread is reasonable
        yes_spread = yes_ask - yes_bid
        no_spread = no_ask - no_bid
        
        if yes_spread > 20 or no_spread > 20:  # >20 cents spread = dead book
            return False, "wide_spread"
        
        # Check there's actual depth
        if not yes.get("depth") and not yes.get("bids"):
            return False, "no_yes_depth"
        
        return True, "ok"
    except Exception as e:
        return False, f"error: {e}"


def find_opportunities():
    """Find micro opportunities with real liquidity."""
    markets = get_open_markets()
    opportunities = []
    
    for m in markets:
        vol = m.get("volume_24h") or 0
        if vol < MIN_LIQUIDITY:
            continue
        
        ticker = m.get("ticker")
        if not ticker:
            continue
        
        viable, reason = check_orderbook_depth(ticker)
        if not viable:
            continue
        
        # Look for cheap YES/NO opportunities
        yes_bid = m.get("yes_bid_dollars", 0)
        yes_ask = m.get("yes_ask_dollars", 1)
        no_bid = m.get("no_bid_dollars", 0)
        no_ask = m.get("no_ask_dollars", 1)
        
        yes_price = yes_ask / 100 if yes_ask else 0
        no_price = no_ask / 100 if no_ask else 0
        
        # Micro strategy: cheap YES or cheap NO
        if yes_price <= 0.15 and yes_price > 0:
            opportunities.append({
                "ticker": ticker,
                "title": m.get("title", ticker),
                "side": "yes",
                "price": yes_price,
                "liquidity": vol,
                "reason": f"cheap_yes_{yes_price:.2f}"
            })
        elif no_price <= 0.15 and no_price > 0:
            opportunities.append({
                "ticker": ticker,
                "title": m.get("title", ticker),
                "side": "no",
                "price": no_price,
                "liquidity": vol,
                "reason": f"cheap_no_{no_price:.2f}"
            })
    
    # Sort by liquidity descending, limit
    opportunities.sort(key=lambda x: x["liquidity"], reverse=True)
    return opportunities[:MAX_POSITIONS]


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"trades": [], "last_run": None}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def grind():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting grind cycle...")
    
    balance = get_balance()
    print(f"Balance: ${balance:.2f}")
    
    if balance < FLOOR:
        print(f"[STOP] Balance ${balance:.2f} below floor ${FLOOR:.2f}. Halting.")
        return
    
    positions = get_positions()
    active_count = len(positions) if isinstance(positions, list) else 0
    print(f"Active positions: {active_count}")
    
    if active_count >= MAX_POSITIONS:
        print(f"[STOP] Max positions {MAX_POSITIONS} reached. Halting.")
        return
    
    
    opportunities = find_opportunities()
    print(f"Found {len(opportunities)} opportunities")
    
    if not opportunities:
        print("[WAIT] No viable opportunities. Sleeping.")
        return
    
    state = load_state()
    
    for opp in opportunities:
        # Skip if we already traded this ticker recently
        recent_tickers = [t["ticker"] for t in state.get("trades", [])[-20:]]
        if opp["ticker"] in recent_tickers:
            continue
        
        # Calculate position size
        alloc = min(MAX_POSITION_SIZE, balance * 0.1)
        shares = max(1, int(alloc / opp["price"]))
        cost = shares * opp["price"]
        
        if cost > balance - FLOOR:
            print(f"[SKIP] Cost ${cost:.2f} would breach floor")
            continue
        
        print(f"[TRADE] {opp['ticker']} {opp['side'].upper()} {shares} @ ${opp['price']:.3f} = ${cost:.2f}")
        
        # Record trade
        trade = {
            "ticker": opp["ticker"],
            "side": opp["side"],
            "shares": shares,
            "price": opp["price"],
            "cost": cost,
            "time": datetime.now(timezone.utc).isoformat(),
            "reason": opp["reason"]
        }
        state.setdefault("trades", []).append(trade)
        save_state(state)
        
        # TODO: actually place order via markets_api.create_order(...)
        # For now, just simulate the trade
        balance -= cost
        print(f"[OK] Simulated trade. Remaining balance: ${balance:.2f}")
        
        if balance < FLOOR:
            print(f"[STOP] Balance ${balance:.2f} below floor after trade. Halting.")
            break
    
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    print(f"[DONE] Grind cycle complete. Balance: ${balance:.2f}")


if __name__ == "__main__":
    grind()
