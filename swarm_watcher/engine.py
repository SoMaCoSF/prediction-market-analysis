"""
swarm_watcher.engine
=====================

The swarm watcher engine: ingest up/down actions, compute per-wallet swarm
profiles, mint GYST UUIDs (0x3F0 wallet, 0x3F2 signal), detect swarm events,
and persist everything to the local SQLite store.

This is the "watcher DB" loop. It is LOCAL and SAFE: it only writes to SQLite
and prints. No exchange calls, no trades, no network. Live Kalshi/Polymarket
ingest is an OPTIONAL, explicitly-passed generator (never auto-fetched here).
"""

from __future__ import annotations

import time
from typing import Iterable, Iterator, List, Optional

from . import gyst_codes
from .math_core import (
    Action,
    profile_all,
    profile_wallet,
    consensus_bias,
    swarm_polarity,
    WalletProfile,
)
from .store import WalletStore


class SwarmWatcher:
    def __init__(self, store: WalletStore, platform: str = "kalshi", dt: float = 1.0, max_lag: int = 5):
        self.store = store
        self.platform = platform
        self.dt = dt
        self.max_lag = max_lag

    # -- ingest ------------------------------------------------------------
    def ingest(self, actions: Iterable[Action]):
        """Persist a batch of actions and roll up wallets."""
        for a in actions:
            # ensure wallet row exists with a GYST 0x3F0 identity
            if self.store.get_wallet(a.wallet) is None:
                g = gyst_codes.mint_wallet_uuid(a.wallet, self.platform)
                self.store.upsert_wallet(a.wallet, g, self.platform, t=a.t)
            self.store.add_tick(a.t, a.wallet, a.market, a.direction, a.size)

    # -- compute + persist signals ----------------------------------------
    def compute_signals(self, as_of: Optional[float] = None) -> List[WalletProfile]:
        """Recompute all wallet profiles from stored ticks, mint 0x3F2 signal
        UUIDs, and persist profiles + signals."""
        as_of = as_of if as_of is not None else time.time()
        ticks = self.store.all_ticks()
        acts = [
            Action(t=row["t"], wallet=row["wallet"], market=row["market"],
                   direction=row["direction"], size=row["size"])
            for row in ticks
        ]
        if not acts:
            return []
        mb = consensus_bias(acts)
        profiles = profile_all(acts, self.dt, self.max_lag)
        for p in profiles:
            sig_uuid = gyst_codes.mint_signal_uuid(p.wallet, p.bias, self.platform)
            self.store.add_signal(p.wallet, sig_uuid, as_of, p.as_dict())
            self.store.save_profile(p.as_dict())
        self._detect_events(acts, mb)
        return profiles

    # -- event detection ---------------------------------------------------
    def _detect_events(self, acts: List[Action], market_bias: float):
        """Emit a market-wide swarm event on significant polarity shifts."""
        pol = swarm_polarity(market_bias)
        # market-wide event whenever we recompute (cheap; dedup by polarity change later)
        self.store.add_event(time.time(), f"SWARM_{pol}", None,
                             f"market_bias={market_bias:.4f}")

    # -- live loop (optional generator) ------------------------------------
    def run(self, source: Iterator[Action], tick_every: int = 50, sleep: float = 0.0):
        """Consume an action generator. `source` yields Action objects.

        Never opens its own network. Pass a generator that you control.
        """
        buf: List[Action] = []
        for a in source:
            buf.append(a)
            if len(buf) >= tick_every:
                self.ingest(buf)
                self.compute_signals()
                buf = []
                if sleep:
                    time.sleep(sleep)
        if buf:
            self.ingest(buf)
            self.compute_signals()
