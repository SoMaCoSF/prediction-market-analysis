#!/usr/bin/env python3
"""Aggressive Kalshi hunter — only trades when real liquidity exists."""
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

# Reuse mission_control auth + proven order path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mission_control import KALSHI_HOST, kalshi_keys, kalshi_post_order, kalshi_sign  # noqa: E402

# ---- Config ----
CASH_FLOOR = 15.00                  # hard floor
POLL_SEC = 15                       # scan frequency
ENTRY_MAX_CENTS = 15                # max entry price
TARGET_CENTS = 8                     # exit target
STOP_CENTS = 2                       # stop loss
MAX_CONTRACTS = 1                    # conservative sizing
MIN_BID_SIZE = 1.0                  # require real counterparty
MIN_ASK_SIZE = 1.0                  # require real counterparty
LIQUIDITY_WINDOW = 300              # 5 min without fills = liquidity dead

# ---- State ----
last_price_by_ticker: dict[str, float] = {}
position: dict[str, dict] = {}

# ---- Logging ----
def log(msg: str) -> None:
    ts = datetime.utcnow().isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        Path("logs/aggressive_hunter.log").write_text(
            Path("logs/aggressive_hunter.log").read_text() + line + "\n"
            if Path("logs/aggressive_hunter.log").exists() else line + "\n"
        )
    except Exception:
        pass


def get_balance() -> float:
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("GET", "/portfolio/balance", ts, kpath)
    h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}
    r = httpx.get(f"{KALSHI_HOST}/portfolio/balance", headers=h, timeout=20)
    return float(r.json().get("balance_dollars", 0))


def get_real_price(ticker: str) -> dict:
    """Return market detail with real price/size from /markets/{ticker}."""
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("GET", f"/markets/{ticker}", ts, kpath)
    h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}
    r = httpx.get(f"{KALSHI_HOST}/markets/{ticker}", headers=h, timeout=20)
    m = r.json().get("market", {})
    return {
        "ticker": ticker,
        "lp": float(m.get("last_price_dollars") or 0) * 100,      # cents
        "yb": float(m.get("yes_bid_dollars") or 0) * 100,
        "ya": float(m.get("yes_ask_dollars") or 0) * 100,
        "ybs": float(m.get("yes_bid_size") or 0),
        "yas": float(m.get("yes_ask_size") or 0),
        "close": m.get("close_time", ""),
    }


def scan_live_markets() -> list[dict]:
    """Scan all 200 markets for real fill signals + live books."""
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("GET", "/markets?limit=200&status=open", ts, kpath)
    h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}
    r = httpx.get(f"{KALSHI_HOST}/markets?limit=200&status=open", headers=h, timeout=20, params={"limit": 200, "status": "open"})
    markets = r.json().get("markets", [])

    now = time.time()
    live = []
    for m in markets:
        ct = m.get("close_time")
        if ct:
            try:
                ct_ts = time.mktime(time.strptime(ct[:19], "%Y-%m-%dT%H:%M:%S"))
                if ct_ts <= now + 120:
                    continue  # expired or closing soon
            except Exception:
                continue

        lp = float(m.get("last_price_dollars") or 0) * 100
        yb = float(m.get("yes_bid_dollars") or 0) * 100
        ya = float(m.get("yes_ask_dollars") or 0) * 100
        ybs = float(m.get("yes_bid_size") or 0)
        yas = float(m.get("yes_ask_size") or 0)
        vol = float(m.get("volume_24h") or 0)

        # Require real liquidity signal
        has_depth = (yb > 0 and ya > 0 and ybs >= MIN_BID_SIZE and yas >= MIN_ASK_SIZE)
        has_recent_fill = lp > 0 and lp < ENTRY_MAX_CENTS

        if has_depth or has_recent_fill:
            live.append({
                "ticker": m.get("ticker"),
                "lp": lp,
                "yb": yb,
                "ya": ya,
                "ybs": ybs,
                "yas": yas,
                "vol": vol,
                "close": ct,
            })
    return live


def buy_entry(ticker: str, price_cents: float) -> bool:
    """Buy YES at given price using proven wrapper."""
    try:
        status, resp = kalshi_post_order({
            "ticker": ticker,
            "side": "yes",
            "count": MAX_CONTRACTS,
            "yes_price": price_cents,
            "client_order_id": f"agg-{int(time.time()*1000)}",
            "type": "limit",
        })
        fill = float(resp.get("fill_count", 0))
        if fill > 0:
            log(f"BUY {ticker} @ {price_cents:.2f}c x{fill}: FILLED")
            position[ticker] = {
                "entry_price": price_cents,
                "qty": int(fill),
                "ts": time.time(),
            }
            return True
        else:
            log(f"BUY SKIP {ticker} @ {price_cents:.2f}c: no fill")
            return False
    except Exception as e:
        log(f"BUY ERR {ticker}: {repr(e)[:100]}")
        return False


def sell_exit(ticker: str, price_cents: float) -> bool:
    """Sell YES (buy NO) at given price using proven wrapper."""
    try:
        status, resp = kalshi_post_order({
            "ticker": ticker,
            "side": "no",
            "count": MAX_CONTRACTS,
            "no_price": price_cents,
            "client_order_id": f"exit-{int(time.time()*1000)}",
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
    """Exit logic: target, stop, or timeout."""
    now = time.time()
    for ticker in list(position.keys()):
        pos = position[ticker]
        entry = pos["entry_price"]
        age = now - pos["ts"]

        # Get current bid
        detail = get_real_price(ticker)
        bid = detail["yb"]

        if bid <= 0:
            # No bid = dead book, try minimum exit
            if age > 30:
                log(f"TIMEOUT {ticker}: forcing exit at 1¢")
                sell_exit(ticker, 1.0)
            continue

        # Target hit
        if bid >= TARGET_CENTS:
            log(f"TARGET {ticker}: bid={bid:.2f}c >= {TARGET_CENTS}c")
            sell_exit(ticker, bid)
        # Stop loss
        elif entry - bid >= STOP_CENTS:
            log(f"STOP {ticker}: entry={entry:.2f}c bid={bid:.2f}c loss={entry-bid:.2f}c")
            sell_exit(ticker, max(bid, 1.0))
        # Timeout
        elif age > 60:
            log(f"TIMEOUT {ticker}: age={age:.0f}s, exiting at {bid:.2f}c")
            sell_exit(ticker, max(bid, 1.0))


def main() -> None:
    log("=== AGGRESSIVE HUNTER STARTING ===")
    cash = get_balance()
    log(f"Initial cash: ${cash:.2f}")

    if cash < CASH_FLOOR:
        log(f"Cash ${cash:.2f} below floor ${CASH_FLOOR:.2f} — waiting")
        sys.exit(0)

    while True:
        try:
            cash = get_balance()
            log(f"cash=${cash:.2f} positions={len(position)}")

            if cash < CASH_FLOOR:
                log(f"Cash ${cash:.2f} below floor — pausing")
                time.sleep(60)
                continue

            # Manage existing positions
            manage_positions()

            # Scan for new entries
            markets = scan_live_markets()
            log(f"Found {len(markets)} live markets")
            for m in markets[:5]:
                log(f"  {m['ticker']}: lp={m['lp']:.2f}c yb={m['yb']:.2f}c ya={m['ya']:.2f}c vol={m['vol']:.1f}")

            # Entry: only if real liquidity exists
            for m in markets:
                ticker = m["ticker"]
                if ticker in position:
                    continue  # already holding

                # Require both bid and ask with size
                if m["yb"] > 0 and m["ya"] > 0 and m["ybs"] >= MIN_BID_SIZE and m["yas"] >= MIN_ASK_SIZE:
                    entry_price = max(m["yb"] + 0.01, min(m["ya"] - 0.01, ENTRY_MAX_CENTS))
                    if entry_price < ENTRY_MAX_CENTS and cash >= entry_price / 100 * MAX_CONTRACTS:
                        log(f"ENTRY SIGNAL {ticker}: bid={m['yb']:.2f}c ask={m['ya']:.2f}c")
                        buy_entry(ticker, entry_price)
                        time.sleep(2)  # let fill settle
                        break  # one entry per cycle

            # Liquidity timeout: if we have positions but no fills in window, pause
            if position:
                oldest_pos_ts = min(p.get("ts", time.time()) for p in position.values())
                if time.time() - oldest_pos_ts > LIQUIDITY_WINDOW:
                    log(f"No fills for {LIQUIDITY_WINDOW}s — liquidity may be dead, pausing")
                    time.sleep(60)

            time.sleep(POLL_SEC)

        except KeyboardInterrupt:
            log("Shutting down")
            sys.exit(0)
        except Exception as e:
            log(f"LOOP ERR: {repr(e)[:200]}")
            time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
