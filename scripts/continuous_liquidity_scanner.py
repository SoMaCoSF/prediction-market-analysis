#!/usr/bin/env python3
"""Continuous Kalshi liquidity scanner — polls 200 markets every 10s, trades on real depth."""
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mission_control import KALSHI_HOST, kalshi_keys, kalshi_post_order, kalshi_sign  # noqa: E402

# ---- Config ----
POLL_SEC = 10                       # scan frequency
MIN_BID_SIZE = 1.0                  # require real bid depth
MIN_ASK_SIZE = 1.0                  # require real ask depth
ENTRY_CENTS = 5                     # buy at 5¢
EXIT_CENTS = 10                     # sell at 10¢
MAX_CONTRACTS = 1                   # conservative sizing
CASH_FLOOR = 0.50                   # hard floor

# ---- State ----
position: dict[str, dict] = {}
last_balance = 0.0

# ---- Logging ----
def log(msg: str) -> None:
    ts = datetime.utcnow().isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        log_path = Path("logs/liquidity_scanner.log")
        log_path.write_text(log_path.read_text() + line + "\n" if log_path.exists() else line + "\n")
    except Exception:
        pass


def get_balance() -> float:
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("GET", "/portfolio/balance", ts, kpath)
    h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}
    r = httpx.get(f"{KALSHI_HOST}/portfolio/balance", headers=h, timeout=20)
    return float(r.json().get("balance_dollars", 0))


def scan_markets() -> list[dict]:
    """Scan all 200 markets and return those with real bid+ask depth."""
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("GET", "/markets?limit=200&status=open", ts, kpath)
    h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}
    r = httpx.get(f"{KALSHI_HOST}/markets?limit=200&status=open", headers=h, timeout=20, params={"limit": 200, "status": "open"})
    markets = r.json().get("markets", [])

    live = []
    for m in markets:
        yb = float(m.get("yes_bid_dollars") or 0) * 100
        ya = float(m.get("yes_ask_dollars") or 0) * 100
        ybs = float(m.get("yes_bid_size") or 0)
        yas = float(m.get("yes_ask_size") or 0)

        # REAL liquidity = both sides with size
        if yb > 0 and ya > 0 and ybs >= MIN_BID_SIZE and yas >= MIN_ASK_SIZE:
            live.append({
                "ticker": m.get("ticker"),
                "yb": yb,
                "ya": ya,
                "ybs": ybs,
                "yas": yas,
            })
    return live


def buy(ticker: str, price_cents: float) -> bool:
    """Buy YES at given price."""
    try:
        status, resp = kalshi_post_order({
            "ticker": ticker,
            "side": "yes",
            "count": MAX_CONTRACTS,
            "yes_price": price_cents,
            "client_order_id": f"scan-buy-{int(time.time()*1000)}",
            "type": "limit",
        })
        fill = float(resp.get("fill_count", 0))
        if fill > 0:
            log(f"BUY {ticker} @ {price_cents:.2f}c x{fill}: FILLED")
            position[ticker] = {"entry": price_cents, "ts": time.time()}
            return True
        else:
            log(f"BUY SKIP {ticker} @ {price_cents:.2f}c: no fill")
            return False
    except Exception as e:
        log(f"BUY ERR {ticker}: {repr(e)[:100]}")
        return False


def sell(ticker: str, price_cents: float) -> bool:
    """Sell YES (buy NO) at given price."""
    try:
        status, resp = kalshi_post_order({
            "ticker": ticker,
            "side": "no",
            "count": MAX_CONTRACTS,
            "no_price": price_cents,
            "client_order_id": f"scan-sell-{int(time.time()*1000)}",
            "type": "limit",
        })
        fill = float(resp.get("fill_count", 0))
        if fill > 0:
            log(f"SELL {ticker} @ {price_cents:.2f}c x{fill}: FILLED")
            position.pop(ticker, None)
            return True
        else:
            log(f"SELL SKIP {ticker} @ {price_cents:.2f}c: no fill")
            return False
    except Exception as e:
        log(f"SELL ERR {ticker}: {repr(e)[:100]}")
        return False


def manage_positions() -> None:
    """Manage open positions: exit at target or stop."""
    for ticker in list(position.keys()):
        pos = position[ticker]
        entry = pos["entry"]
        age = time.time() - pos["ts"]

        # Get current bid
        kid, kpath = kalshi_keys()
        ts = str(int(time.time() * 1000))
        sig = kalshi_sign("GET", f"/markets/{ticker}", ts, kpath)
        h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}
        r = httpx.get(f"{KALSHI_HOST}/markets/{ticker}", headers=h, timeout=20)
        m = r.json().get("market", {})
        yb = float(m.get("yes_bid_dollars") or 0) * 100

        if yb <= 0:
            # No bid = dead book
            if age > 60:
                log(f"TIMEOUT {ticker}: no bid for 60s, forcing exit at 1¢")
                sell(ticker, 1.0)
            continue

        # Target hit
        if yb >= EXIT_CENTS:
            log(f"TARGET {ticker}: bid={yb:.2f}c >= {EXIT_CENTS}c")
            sell(ticker, yb)
        # Stop loss
        elif entry - yb >= 5:
            log(f"STOP {ticker}: entry={entry:.2f}c bid={yb:.2f}c")
            sell(ticker, max(yb, 1.0))


def main() -> None:
    log("=== CONTINUOUS LIQUIDITY SCANNER STARTING ===")
    last_balance = get_balance()
    log(f"Initial balance: ${last_balance:.2f}")

    while True:
        try:
            balance = get_balance()
            if balance != last_balance:
                log(f"Balance changed: ${last_balance:.2f} -> ${balance:.2f}")
                last_balance = balance

            if balance < CASH_FLOOR:
                log(f"Balance ${balance:.2f} below floor ${CASH_FLOOR:.2f} — pausing")
                time.sleep(60)
                continue

            # Manage existing positions
            if position:
                manage_positions()

            # Scan for liquidity
            markets = scan_markets()
            if markets:
                log(f"LIQUIDITY FOUND: {len(markets)} markets with real depth")
                for m in markets[:3]:
                    log(f"  {m['ticker']}: bid={m['yb']:.2f}c ask={m['ya']:.2f}c bid_size={m['ybs']} ask_size={m['yas']}")
                    # Enter if not already holding
                    if m['ticker'] not in position and balance >= ENTRY_CENTS / 100:
                        buy(m['ticker'], ENTRY_CENTS)
                        break
            else:
                log("No liquidity in any market")

            time.sleep(POLL_SEC)

        except KeyboardInterrupt:
            log("Shutting down")
            sys.exit(0)
        except Exception as e:
            log(f"LOOP ERR: {repr(e)[:200]}")
            time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
