"""
swarm_watcher.math_core
=======================

Up/Down Signal Swarm mathematics.

Core idea (from user): follow live up/down signals per wallet. Evaluate the
RATIO of up vs down actions for each wallet, compare wallets against each other
("down-signal swarm vs up-signal response"), detect who is pushing which
direction, and score their bidding patterns. Each wallet + each derived signal
gets a GYST UUIDv8 (0x3F0 wallet, 0x3F2 trader-signal) in the substrate.

All functions are PURE and numpy-friendly so they can be unit-tested in isolation
without a database or network. Times are unix seconds (float).

Sign convention
---------------
direction: +1 = UP (bid/long/yes-buy pressure), -1 = DOWN (ask/short/no-buy).
A wallet's swarm_bias in [0,1] = fraction of its actions that were UP.
0.5 = neutral. >0.5 = net upward swarm. <0.5 = net downward swarm.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

import numpy as np

EPS = 1e-9


@dataclass
class Action:
    """A single market action attributed to a wallet."""
    t: float           # unix seconds
    wallet: str
    market: str
    direction: int     # +1 up, -1 down
    size: float = 1.0  # notional weight (defaults to 1 count)


# ---------------------------------------------------------------------------
# Per-wallet up/down ratio
# ---------------------------------------------------------------------------

def swarm_bias(actions: Sequence[Action]) -> float:
    """Fraction of UP actions for a single wallet's action stream.

    Returns 0.5 for empty input (neutral, no evidence). Range [0,1].
    """
    if not actions:
        return 0.5
    ups = sum(1 for a in actions if a.direction > 0)
    total = len(actions)
    return ups / total


def up_down_counts(actions: Sequence[Action]) -> Tuple[int, int]:
    ups = sum(1 for a in actions if a.direction > 0)
    downs = sum(1 for a in actions if a.direction < 0)
    return ups, downs


def swarm_bias_weighted(actions: Sequence[Action]) -> float:
    """Size-weighted swarm bias (notional-weighted instead of count-weighted)."""
    if not actions:
        return 0.5
    up_w = sum(a.size for a in actions if a.direction > 0)
    down_w = sum(a.size for a in actions if a.direction < 0)
    total = up_w + down_w
    if total <= EPS:
        return 0.5
    return up_w / total


# ---------------------------------------------------------------------------
# Cross-wallet divergence (who is pushing up vs down vs whom)
# ---------------------------------------------------------------------------

def wallet_bias_map(actions: Sequence[Action]) -> Dict[str, float]:
    """Map wallet -> swarm_bias across the whole action stream."""
    by_wallet: Dict[str, List[Action]] = defaultdict(list)
    for a in actions:
        by_wallet[a.wallet].append(a)
    return {w: swarm_bias(acts) for w, acts in by_wallet.items()}


def swarm_divergence(a: float, b: float) -> float:
    """Directed divergence d = a - b in [-1,1].

    d > 0  => wallet A is more UP-biased than B (A pushes up relative to B).
    d < 0  => A is more DOWN-biased than B.
    d = 0  => same bias (no relative signal).
    """
    return a - b


def consensus_bias(actions: Sequence[Action]) -> float:
    """Aggregate swarm bias of ALL wallets combined (the 'market swarm')."""
    return swarm_bias(actions)


def contrarian_score(wallet_bias: float, market_bias: float) -> float:
    """How contrarian a wallet is vs the market swarm.

    Returns value in [-1,1]:
      +1  => wallet is maximally DOWN while market is UP (pure contrarian-down)
      -1  => wallet is maximally UP while market is DOWN (pure contrarian-up)
       0  => wallet tracks the market exactly.
    Defined as contrarian = (market_bias - wallet_bias) signed so that
    being opposite the crowd is positive.
    """
    return (market_bias - wallet_bias) * 2.0  # *2 maps [-0.5,0.5] -> [-1,1]


# ---------------------------------------------------------------------------
# Temporal pattern: does a wallet LEAD the swarm? (autocorrelation / lag)
# ---------------------------------------------------------------------------

def direction_series(actions: Sequence[Action], dt: float = 1.0) -> Tuple[np.ndarray, np.ndarray]:
    """Bucket actions into uniform time bins; return (bin_centers, signed_flow).

    signed_flow[i] = (ups - downs) in bin i. Bin width = dt seconds.
    Bins are indexed from min(t) to max(t).
    """
    if not actions:
        return np.array([]), np.array([])
    ts = np.array([a.t for a in actions], dtype=float)
    dirs = np.array([a.direction for a in actions], dtype=float)
    t0, t1 = ts.min(), ts.max()
    if t1 - t0 < dt:
        # single bin
        return np.array([(t0 + t1) / 2.0]), np.array([dirs.sum()])
    n_bins = int(math.ceil((t1 - t0) / dt))
    idx = np.floor((ts - t0) / dt).astype(int)
    idx = np.clip(idx, 0, n_bins - 1)
    flow = np.zeros(n_bins, dtype=float)
    for i, d in zip(idx, dirs):
        flow[i] += d
    centers = t0 + (np.arange(n_bins) + 0.5) * dt
    return centers, flow


def lead_autocorrelation(flow: np.ndarray, max_lag: int = 5) -> np.ndarray:
    """Autocorrelation of signed flow at lags 0..max_lag (Pearson, zero-mean).

    Lag-0 is always 1.0 by definition. Higher lag persistence indicates a
    wallet whose directional pressure is self-correlated (sticky swarm) vs
    mean-reverting (random). Returns array length max_lag+1.
    """
    if flow.size == 0:
        return np.array([1.0] * (max_lag + 1))
    x = flow - flow.mean()
    denom = np.dot(x, x)
    if denom <= EPS:
        return np.array([1.0] * (max_lag + 1))
    out = np.empty(max_lag + 1)
    for lag in range(max_lag + 1):
        if lag >= x.size:
            out[lag] = 0.0
            continue
        y = np.concatenate([x[lag:], np.zeros(lag)])
        out[lag] = np.dot(x, y) / denom
    return out


def stickiness(flow: np.ndarray, max_lag: int = 5) -> float:
    """Summary 'stickiness' = mean autocorrelation over lags 1..max_lag.

    1.0 = perfectly persistent directional swarm; 0.0 = no persistence
    (random); negative = mean-reverting.
    """
    ac = lead_autocorrelation(flow, max_lag)
    if ac.size <= 1:
        return 0.0
    return float(np.mean(ac[1:]))


# ---------------------------------------------------------------------------
# Composite wallet pattern profile
# ---------------------------------------------------------------------------

@dataclass
class WalletProfile:
    wallet: str
    n_actions: int
    up: int
    down: int
    bias: float                 # [0,1] up fraction
    bias_weighted: float
    market_bias: float          # aggregate swarm bias over same window
    contrarian: float           # [-1,1]
    stickiness: float           # temporal persistence of direction
    divergence_vs_market: float # bias - market_bias

    def as_dict(self) -> dict:
        return {
            "wallet": self.wallet,
            "n_actions": self.n_actions,
            "up": self.up,
            "down": self.down,
            "bias": round(self.bias, 4),
            "bias_weighted": round(self.bias_weighted, 4),
            "market_bias": round(self.market_bias, 4),
            "contrarian": round(self.contrarian, 4),
            "stickiness": round(self.stickiness, 4),
            "divergence_vs_market": round(self.divergence_vs_market, 4),
            "polarity": swarm_polarity(self.bias),
        }


def profile_wallet(
    wallet: str,
    actions: Sequence[Action],
    market_bias: float,
    dt: float = 1.0,
    max_lag: int = 5,
) -> WalletProfile:
    """Build a full pattern profile for one wallet against the market swarm."""
    wacts = [a for a in actions if a.wallet == wallet]
    up, down = up_down_counts(wacts)
    flow = direction_series(wacts, dt)[1]
    return WalletProfile(
        wallet=wallet,
        n_actions=len(wacts),
        up=up,
        down=down,
        bias=swarm_bias(wacts),
        bias_weighted=swarm_bias_weighted(wacts),
        market_bias=market_bias,
        contrarian=contrarian_score(swarm_bias(wacts), market_bias),
        stickiness=stickiness(flow, max_lag),
        divergence_vs_market=swarm_bias(wacts) - market_bias,
    )


def profile_all(
    actions: Sequence[Action],
    dt: float = 1.0,
    max_lag: int = 5,
) -> List[WalletProfile]:
    """Profile every wallet in the stream against the collective swarm."""
    mb = consensus_bias(actions)
    wallets = sorted({a.wallet for a in actions})
    return [profile_wallet(w, actions, mb, dt, max_lag) for w in wallets]


# ---------------------------------------------------------------------------
# Swarm "event" detection: a wallet flips or a swarm converges/diverges
# ---------------------------------------------------------------------------

def swarm_polarity(bias: float) -> str:
    """Label a bias: STRONG_UP / UP / NEUTRAL / DOWN / STRONG_DOWN."""
    if bias >= 0.75:
        return "STRONG_UP"
    if bias >= 0.55:
        return "UP"
    if bias <= 0.25:
        return "STRONG_DOWN"
    if bias <= 0.45:
        return "DOWN"
    return "NEUTRAL"
