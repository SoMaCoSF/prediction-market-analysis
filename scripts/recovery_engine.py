# file_id: SOM-PY-1101-v1.0.0 name: recovery_engine.py description: Stuck-capital recovery — liquidates dead event positions at live bid, recovers cash, hands it to the guarded scalp loop. Fee-safe: only sells; never pays entry fees. project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [recovery, liquidity, self-fund] created: 2026-08-05 version: 1.0.0 agent_id: HERMES-AGENT
"""recovery_engine.py — turn stranded equity into tradeable cash.

The account was ground to dust by micro-clip fees. What survived is ~$1.83
locked in long-dated EVENT positions (KXMLB-26, KXNBA-27, cross-category
mults) that the 15-min scalp loop can NEVER trade. This engine:

  1. Reads every open position from the exchange truth.
  2. Liquidates positions in DEAD/closed/long-dated markets at their live bid
     (a SELL = no entry fee, recovers real cash).
  3. Skips any position still in an ACTIVE 15-min market (those are the scalp
     loop's job, don't interfere).
  4. Does NOT pay a single entry fee — selling realizes cash, it doesn't burn it.

Run headless under the supervisor. Polls every RECOVER_POLL_S.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import runlog  # noqa: E402

RECOVER_POLL_S = 120
# Markets matching these series are scalp-loop live (leave them alone).
LIVE_SERIES = ("KXBTC15M", "KXETH15M", "KXSOL15M", "KXXRP15M", "KXDOGE15M")


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] [recover] {m}", flush=True)
    runlog.log_event("recover", m)


def open_positions():
    """Exchange truth: list of (ticker, fp, side, market_status, yes_bid_c)."""
    import vault
    pos = vault.kget("/portfolio/positions")
    out = []
    for mp in pos.get("market_positions", []):
        t = mp.get("ticker", "")
        fp = float(mp.get("position_fp") or 0)
        if fp <= 0:
            continue
        # live quote for the ticker
        mk = vault.kget(f"/markets/{t}")
        m = mk.get("market") or {}
        status = m.get("status")
        yb = float(m.get("yes_bid_dollars") or 0) * 100
        side = mp.get("side") or "yes"
        out.append({"ticker": t, "fp": fp, "side": side,
                    "status": status, "yes_bid_c": yb})
    return out


def recoverable(positions):
    """Positions we can liquidate for cash without breaking the live loop."""
    out = []
    for p in positions:
        # skip live 15-min scalp markets — those are the loop's to trade
        if any(p["ticker"].startswith(s) for s in LIVE_SERIES):
            continue
        # only sell if there's a real bid (market has liquidity)
        if p["yes_bid_c"] > 0 and p["status"] in (None, "open", "closed", "settled"):
            out.append(p)
    return out


def liquidate(p):
    """SELL the position's yes side at the live bid. Returns filled cash or 0."""
    import vault
    # To close a YES long: sell yes. To close a NO long: sell no.
    side = p["side"]
    price_c = int(p["yes_bid_c"]) if side == "yes" else int(100 - p["yes_bid_c"])
    if price_c <= 0 or price_c >= 100:
        return 0.0
    r = vault.korder(p["ticker"], side, "sell", int(p["fp"]), price_c)
    if r.get("order") or r.get("ok"):
        filled = float((r.get("order") or {}).get("filled_qty") or 0)
        log(f"LIQUIDATED {p['ticker']} x{int(p['fp'])} @ {price_c}c side={side} -> filled {filled}")
        return filled * price_c / 100.0
    log(f"liquidate rejected {p['ticker']}: {str(r.get('error'))[:60]}")
    return 0.0


def main():
    fleetlib.acquire_lock("recover")
    log("recovery start — liquidating stranded event positions")
    recovered = 0.0
    while True:
        try:
            fleetlib.checkin("recover")
            positions = open_positions()
            targets = recoverable(positions)
            for p in targets:
                got = liquidate(p)
                recovered += got
                time.sleep(1)
            if targets:
                log(f"recovery pass: {len(targets)} positions, +${recovered:.2f} realized")
            else:
                log("no stranded positions left to recover — standing down")
                # nothing to do; the scalp loop handles live markets. Sleep long.
                time.sleep(RECOVER_POLL_S * 5)
                continue
        except Exception as e:
            log(f"warn {repr(e)[:80]}")
        time.sleep(RECOVER_POLL_S)


if __name__ == "__main__":
    main()
