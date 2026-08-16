"""Up/Down Signal Swarm watcher — local corpus builder.

 evaluate per-wallet up/down ratios, compare swarms, detect who pushes which
 direction, score bidding patterns, and mint GYST UUIDv8 (0x3F0 wallet,
 0x3F2 signal). Local-only: writes to SQLite, no exchange calls.
"""

from .math_core import (
    Action, swarm_bias, swarm_bias_weighted, up_down_counts,
    wallet_bias_map, swarm_divergence, consensus_bias, contrarian_score,
    direction_series, lead_autocorrelation, stickiness,
    profile_wallet, profile_all, swarm_polarity, WalletProfile,
)
from .gyst_codes import (
    encode_gyst, mint_wallet_uuid, mint_signal_uuid,
    TYPE_TRADER_WALLET, TYPE_TRADER_SIGNAL,
)
from .store import WalletStore
from .engine import SwarmWatcher

__all__ = [
    "Action", "swarm_bias", "swarm_bias_weighted", "up_down_counts",
    "wallet_bias_map", "swarm_divergence", "consensus_bias", "contrarian_score",
    "direction_series", "lead_autocorrelation", "stickiness",
    "profile_wallet", "profile_all", "swarm_polarity", "WalletProfile",
    "encode_gyst", "mint_wallet_uuid", "mint_signal_uuid",
    "TYPE_TRADER_WALLET", "TYPE_TRADER_SIGNAL",
    "WalletStore", "SwarmWatcher",
]
