#!/usr/bin/env python3
"""Multi-venue liquidity router — chooses Kalshi or Polymarket based on real depth."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import httpx  # noqa: E402

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
POLY_GAMMA = "https://gamma-api.polymarket.com"


def kalshi_depth() -> dict:
    """Check Kalshi for real executable depth."""
    try:
        r = httpx.get(f"{KALSHI}/markets", params={"limit": 200, "status": "open"}, timeout=20)
        markets = r.json().get("markets", [])
        real_depth = []
        for m in markets:
            yb = float(m.get("yes_bid_dollars") or 0)
            ya = float(m.get("yes_ask_dollars") or 0)
            vol = float(m.get("volume_24h_fp") or m.get("volume_24h") or 0)
            if yb > 0 and ya > 0 and vol > 0:
                real_depth.append({
                    "ticker": m["ticker"],
                    "yes_bid": yb * 100,
                    "yes_ask": ya * 100,
                    "volume_24h": vol,
                })
        return {
            "venue": "kalshi",
            "ok": True,
            "markets_with_depth": len(real_depth),
            "best": real_depth[:5] if real_depth else [],
        }
    except Exception as exc:
        return {"venue": "kalshi", "ok": False, "error": repr(exc)[:100]}


def polymarket_depth() -> dict:
    """Check Polymarket for real volume/activity."""
    try:
        r = httpx.get(f"{POLY_GAMMA}/markets", params={"limit": 100, "active": "true", "order": "volume24hr", "ascending": "false"}, timeout=20)
        markets = r.json()
        active = [m for m in markets if float(m.get("volume24hr") or m.get("volume") or 0) > 0]
        return {
            "venue": "polymarket",
            "ok": True,
            "markets_with_volume": len(active),
            "best": active[:5],
        }
    except Exception as exc:
        return {"venue": "polymarket", "ok": False, "error": repr(exc)[:100]}


def route_trade() -> dict:
    """Return which venue has the best executable liquidity right now."""
    kalshi = kalshi_depth()
    poly = polymarket_depth()
    k_score = kalshi.get("markets_with_depth", 0)
    p_score = poly.get("markets_with_volume", 0)
    if k_score > 0 and k_score >= p_score:
        return {"route_to": "kalshi", "reason": f"kalshi has {k_score} markets with real depth", "kalshi": kalshi, "polymarket": poly}
    if p_score > 0:
        return {"route_to": "polymarket", "reason": f"polymarket has {p_score} active markets with volume", "kalshi": kalshi, "polymarket": poly}
    return {"route_to": "none", "reason": "no executable depth in either venue", "kalshi": kalshi, "polymarket": poly}


if __name__ == "__main__":
    print(route_trade())
