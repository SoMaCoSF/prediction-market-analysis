"""
swarm_watcher.demo
=================

Local, network-free demonstration of the Up/Down Signal Swarm corpus builder.

Builds a SYNTHETIC swarm of wallets with distinct up/down behaviors, ingests
them, computes profiles, mints GYST UUIDs, and prints a readable corpus table.
No exchange calls. Run:  python -m swarm_watcher.demo
"""

from __future__ import annotations

import os
import tempfile

from . import gyst_codes
from .engine import SwarmWatcher
from .math_core import Action, profile_all, wallet_bias_map, consensus_bias, swarm_polarity
from .store import WalletStore


def synthetic_swarm() -> list[Action]:
    """Three wallets with intentional, legible behaviors.

    W_UP     — relentlessly bids UP (net upward swarm)
    W_DOWN   — relentlessly bids DOWN (net downward swarm / 'dump' swarm)
    W_CONTRA — contrarian: mostly opposite the crowd, sticky direction
    """
    acts: list[Action] = []
    t = 1000.0
    # W_UP: 18 up, 2 down
    for i in range(18):
        acts.append(Action(t, "W_UP", f"M{i%5}", +1)); t += 1
    for i in range(2):
        acts.append(Action(t, "W_UP", f"M{i%5}", -1)); t += 1
    # W_DOWN: 2 up, 18 down
    for i in range(2):
        acts.append(Action(t, "W_DOWN", f"M{i%5}", +1)); t += 1
    for i in range(18):
        acts.append(Action(t, "W_DOWN", f"M{i%5}", -1)); t += 1
    # W_CONTRA: sticky alternating blocks (5 up then 5 down) -> contrarian vs market, high stickiness
    for i in range(5):
        acts.append(Action(t, "W_CONTRA", f"M{i%5}", +1)); t += 1
    for i in range(5):
        acts.append(Action(t, "W_CONTRA", f"M{i%5}", -1)); t += 1
    for i in range(5):
        acts.append(Action(t, "W_CONTRA", f"M{i%5}", +1)); t += 1
    for i in range(5):
        acts.append(Action(t, "W_CONTRA", f"M{i%5}", -1)); t += 1
    return acts


def main():
    fd, dbpath = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(dbpath)
    try:
        store = WalletStore(dbpath)
        watcher = SwarmWatcher(store)

        print("=" * 78)
        print("UP/DOWN SIGNAL SWARM — LOCAL CORPUS DEMO (no network)")
        print("=" * 78)

        acts = synthetic_swarm()
        watcher.ingest(acts)
        profs = watcher.compute_signals()

        # ---- corpus table ----
        mb = consensus_bias(acts)
        print(f"\nMARKET SWARM bias (all wallets combined): {mb:.3f}  [{swarm_polarity(mb)}]")
        print("-" * 78)
        print(f"{'WALLET':<12}{'N':>5}{'UP':>5}{'DN':>5}{'BIAS':>8}{'CONT':>8}{'STICK':>8}{'POLARITY':>14}")
        print("-" * 78)
        for p in sorted(profs, key=lambda x: -abs(x.divergence_vs_market)):
            print(f"{p.wallet:<12}{p.n_actions:>5}{p.up:>5}{p.down:>5}"
                  f"{p.bias:>8.3f}{p.contrarian:>8.2f}{p.stickiness:>8.3f}"
                  f"{swarm_polarity(p.bias):>14}")

        # ---- GYST UUIDs minted ----
        print("-" * 78)
        print("GYST UUIDv8 identities minted:")
        for w in ["W_UP", "W_DOWN", "W_CONTRA"]:
            row = store.get_wallet(w)
            sig = store.conn.execute("SELECT gyst_uuid FROM signals WHERE wallet=? ORDER BY t DESC LIMIT 1", (w,)).fetchone()
            wuuid = row["gyst_uuid"] if row else "?"
            suuid = sig["gyst_uuid"] if sig else "?"
            print(f"  {w:<12} wallet={wuuid}  signal={suuid}")

        # ---- who is pushing up vs down vs whom ----
        print("-" * 78)
        bm = wallet_bias_map(acts)
        up_w = [w for w, b in bm.items() if b > 0.6]
        dn_w = [w for w, b in bm.items() if b < 0.4]
        print(f"UP-swarm wallets   : {up_w}")
        print(f"DOWN-swarm wallets : {dn_w}")
        print(f"Divergence W_UP - W_DOWN = {bm['W_UP'] - bm['W_DOWN']:+.3f}  (positive => W_UP pushes up relative to W_DOWN)")

        print("=" * 78)
        print(f"DB written to: {dbpath}")
        print("Inspect: sqlite3", dbpath, "'.tables' / 'SELECT * FROM wallet_profiles;'")
        store.close()
    finally:
        if os.path.exists(dbpath):
            os.remove(dbpath)


if __name__ == "__main__":
    main()
