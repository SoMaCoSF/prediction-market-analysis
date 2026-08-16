"""
swarm_watcher.corpus_view
=========================

Produces the exact serializable view a dashboard needs from the local store:
wallet table (sorted by |divergence|), market swarm summary, recent swarm
events, and the GYST UUIDs. Pure read layer over WalletStore.

NOT deployed. This is the contract a future dashboard (local or Vercel) consumes.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .store import WalletStore
from .math_core import swarm_polarity


def build_corpus_view(store: WalletStore) -> Dict[str, Any]:
    """Assemble the dashboard corpus view from the local store."""
    profiles = store.profiles()  # already sorted by |divergence_vs_market| DESC

    wallets = []
    for p in profiles:
        # latest signal UUID for this wallet
        sig = store.conn.execute(
            "SELECT gyst_uuid, bias, polarity FROM signals WHERE wallet=? ORDER BY t DESC LIMIT 1",
            (p["wallet"],),
        ).fetchone()
        wrow = store.get_wallet(p["wallet"])
        wallets.append({
            "wallet": p["wallet"],
            "gyst_wallet": wrow["gyst_uuid"] if wrow else None,
            "gyst_signal": sig["gyst_uuid"] if sig else None,
            "n_actions": p["n_actions"],
            "up": p["up"],
            "down": p["down"],
            "bias": p["bias"],
            "bias_weighted": p["bias_weighted"],
            "market_bias": p["market_bias"],
            "contrarian": p["contrarian"],
            "stickiness": p["stickiness"],
            "divergence_vs_market": p["divergence_vs_market"],
            "polarity": swarm_polarity(p["bias"]),
        })

    events = [
        {"t": e["t"], "kind": e["kind"], "wallet": e["wallet"], "detail": e["detail"]}
        for e in store.events()[:25]
    ]

    # market swarm summary
    total_up = sum(p["up"] for p in profiles)
    total_down = sum(p["down"] for p in profiles)
    market_bias = (total_up / (total_up + total_down)) if (total_up + total_down) else 0.5

    up_swarm = [w["wallet"] for w in wallets if w["bias"] > 0.6]
    down_swarm = [w["wallet"] for w in wallets if w["bias"] < 0.4]

    return {
        "market_bias": round(market_bias, 4),
        "market_polarity": swarm_polarity(market_bias),
        "total_wallets": len(wallets),
        "up_swarm": up_swarm,
        "down_swarm": down_swarm,
        "wallets": wallets,
        "events": events,
    }
