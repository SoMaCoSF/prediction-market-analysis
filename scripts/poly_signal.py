"""Polymarket signal source for live trading fallback.

Provides get_live_poly_markets() which returns markets sorted by volume/activity.
Returns None on failure so callers can fall back cleanly.
"""

from __future__ import annotations

import logging
from typing import Any

from src.indexers.polymarket.client import PolymarketClient

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_outcome_prices(raw: str | None) -> tuple[float, float]:
    try:
        if not raw:
            return 0.0, 0.0
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if len(parts) >= 2:
            return float(parts[0]), float(parts[1])
    except (TypeError, ValueError):
        pass
    return 0.0, 0.0


def get_live_poly_markets(limit: int = 50) -> list[dict[str, Any]] | None:
    markets: list[dict[str, Any]] = []
    try:
        with PolymarketClient() as client:
            for page, _offset in client.iter_markets(limit=min(limit, 100)):
                if not page:
                    break
                for m in page:
                    try:
                        yes_p, _ = _parse_outcome_prices(m.outcome_prices)
                        volume = _safe_float(m.volume)
                        liquidity = _safe_float(m.liquidity)
                        if yes_p <= 0 or yes_p >= 1:
                            continue
                        if volume <= 0 and liquidity <= 0:
                            continue
                        markets.append(
                            {
                                "id": m.id,
                                "slug": m.slug or m.id,
                                "question": m.question or m.slug or m.id,
                                "yes_price": yes_p,
                                "no_price": 1.0 - yes_p,
                                "volume_24h": volume,
                                "liquidity": liquidity,
                                "end_date": m.end_date,
                                "active": m.active,
                            }
                        )
                    except Exception:
                        continue
                if len(markets) >= limit:
                    break
    except Exception as exc:
        logger.warning("poly signal ERR: %s", exc)
        return None
    markets.sort(key=lambda m: m.get("volume_24h", 0), reverse=True)
    return markets[:limit]
