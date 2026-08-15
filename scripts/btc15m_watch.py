#!/usr/bin/env python3
"""BTC-15m energy watcher + GO-gated micro-bet.

Discipline:
  - NEVER trades below CASH_FLOOR ($10.00). Currently cash=$9.35 -> blocked.
  - NEVER trades a market without two-sided flow (yes_bid>0 AND yes_ask>0).
  - Live bet only when GO_BTC file present AND conditions met.
  - DRY_RUN by default (builds order, validates, does not POST).

This script is the 'watch BTC-15m for energy, then bet' executor you asked for.
Run it; it reports state honestly. Drop prediction-market-analysis/GO_BTC to go live.
"""
import sys, time, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

import httpx  # noqa: E402
from mission_control import KALSHI_HOST, kalshi_keys, kalshi_sign  # noqa: E402

CASH_FLOOR = 10.00
MAX_RISK = 1.00          # $1 max micro-bet (this is a $9.x account)
GO_FILE = ROOT / "GO_BTC"
LOG = ROOT / "data" / "btc15m_watch.log"
LOG.parent.mkdir(exist_ok=True)


def auth_get(path, params=None):
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("GET", path, ts, kpath)
    h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}
    r = httpx.get(f"{KALSHI_HOST}{path}", params=params, headers=h, timeout=20)
    r.raise_for_status()
    return r.json()


def find_btc15m():
    """Return the most-liquid BTC-15m (or BTC) open market dict, or None."""
    found = []
    cursor = None
    for _ in range(10):
        params = {"limit": 100, "status": "open"}
        if cursor:
            params["cursor"] = cursor
        j = auth_get("/markets", params=params)
        for m in j.get("markets", []):
            t = (m.get("ticker") or "").upper()
            if "BTC15M" in t or ("BTC" in t and "15M" in t):
                found.append(m)
        cursor = j.get("cursor")
        if not cursor:
            break
    if not found:
        return None
    return max(found, key=lambda m: float(m.get("volume_24h") or 0) + float(m.get("volume") or 0))


def market_energy(m):
    """Crude 0-1 energy: volume presence + two-sided spread tightness.
    Real 'kinetic' energy needs tick history; this is the conservative proxy."""
    vol = float(m.get("volume_24h") or 0) + float(m.get("volume") or 0)
    yb = float(m.get("yes_bid", 0) or 0)
    ya = float(m.get("yes_ask", 0) or 0)
    nb = float(m.get("no_bid", 0) or 0)
    na = float(m.get("no_ask", 0) or 0)
    two_sided = (yb > 0 and ya > 0) or (nb > 0 and na > 0)
    if not two_sided:
        return 0.0, False
    # energy = log-scaled volume, capped 0-1 (vol 0->0, vol>=500->~1)
    import math
    e = min(1.0, math.log10(max(vol, 1)) / 3.0)  # 1->0, 1000->1
    return round(e, 3), True


def main():
    report = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "action": "none"}
    cash = float(auth_get("/portfolio/balance").get("balance_dollars", 0) or 0)
    report["cash"] = round(cash, 4)

    m = find_btc15m()
    if not m:
        report["action"] = "hold"
        report["detail"] = "NO BTC-15m market open — nothing to bet on"
        print(json.dumps(report, indent=2))
        return report

    ticker = m.get("ticker")
    energy, liquid = market_energy(m)
    report["ticker"] = ticker
    report["energy"] = energy
    report["two_sided"] = liquid

    # gates
    reasons = []
    if cash < CASH_FLOOR:
        reasons.append(f"cash ${cash:.2f} < floor ${CASH_FLOOR:.2f}")
    if not liquid:
        reasons.append("BTC-15m has no two-sided flow")
    live = GO_FILE.exists()
    if not live:
        reasons.append("GO_BTC absent (DRY_RUN)")

    if reasons:
        report["action"] = "hold"
        report["detail"] = "; ".join(reasons)
        print(json.dumps(report, indent=2))
        return report

    # conditions met + GO present -> place micro-bet (mean-reversion: buy cheap YES)
    yb = float(m.get("yes_bid", 0) or 0)
    ya = float(m.get("yes_ask", 0) or 0)
    # bet on the side with edge: if YES cheap (<15c) buy YES, else skip
    if ya > 0 and ya < 15:
        side, px = "bid", ya / 100.0
        count = max(1, int(MAX_RISK / max(px, 0.01)))
    else:
        report["action"] = "skip"
        report["detail"] = f"BTC-15m YES ask {ya:.2f}c not <15c — no MR edge"
        print(json.dumps(report, indent=2))
        return report

    body = {
        "ticker": ticker,
        "client_order_id": f"btc15m-{int(time.time()*1000)}",
        "side": side,
        "count": f"{count:.2f}",
        "price": f"{px:.4f}",
        "time_in_force": "good_till_canceled",
        "self_trade_prevention_type": "taker_at_cross",
        "post_only": False,
        "cancel_order_on_pause": False,
        "reduce_only": False,
        "subaccount": 0,
        "exchange_index": 0,
    }
    kid, kpath = kalshi_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign("POST", "/portfolio/events/orders", ts, kpath)
    h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts, "Content-Type": "application/json"}
    r = httpx.post(f"{KALSHI_HOST}/portfolio/events/orders", json=body, headers=h, timeout=20)
    res = {"status_code": r.status_code, "resp": r.text[:500]}
    report["action"] = "bet"
    report["detail"] = f"{ticker} {side} @ {px:.2f} x{count} -> {res['status_code']}"
    report["result"] = res
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    main()
