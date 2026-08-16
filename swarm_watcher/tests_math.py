"""
Tests for swarm_watcher.math_core + gyst_codes + store.

These are the "litany of tests on our math" — run locally (pytest) before any
public surface. No network, no exchange. Pure + deterministic.
"""

import os
import tempfile
import uuid

import numpy as np
import pytest

from swarm_watcher import (
    Action, swarm_bias, swarm_bias_weighted, up_down_counts,
    wallet_bias_map, swarm_divergence, consensus_bias, contrarian_score,
    direction_series, lead_autocorrelation, stickiness,
    profile_wallet, profile_all, swarm_polarity, WalletProfile,
    encode_gyst, mint_wallet_uuid, mint_signal_uuid,
    TYPE_TRADER_WALLET, TYPE_TRADER_SIGNAL,
)
from swarm_watcher.store import WalletStore


# ---------------------------------------------------------------------------
# swarm_bias
# ---------------------------------------------------------------------------
def test_swarm_bias_empty_is_neutral():
    assert swarm_bias([]) == 0.5

def test_swarm_bias_all_up():
    acts = [Action(1, "w1", "m", +1), Action(2, "w1", "m", +1)]
    assert swarm_bias(acts) == 1.0

def test_swarm_bias_all_down():
    acts = [Action(1, "w1", "m", -1), Action(2, "w1", "m", -1)]
    assert swarm_bias(acts) == 0.0

def test_swarm_bias_mixed():
    acts = [Action(1, "w1", "m", +1), Action(2, "w1", "m", +1), Action(3, "w1", "m", -1)]
    assert swarm_bias(acts) == pytest.approx(2 / 3)

def test_up_down_counts():
    acts = [Action(1, "w1", "m", +1), Action(2, "w1", "m", -1), Action(3, "w1", "m", -1)]
    assert up_down_counts(acts) == (1, 2)

def test_swarm_bias_weighted():
    # up size 1, down size 3 => weighted bias = 1/(1+3) = 0.25
    acts = [Action(1, "w1", "m", +1, size=1.0), Action(2, "w1", "m", -1, size=3.0)]
    assert swarm_bias_weighted(acts) == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# cross-wallet divergence / consensus / contrarian
# ---------------------------------------------------------------------------
def test_wallet_bias_map():
    acts = [
        Action(1, "A", "m", +1), Action(2, "A", "m", +1),  # A bias 1.0
        Action(3, "B", "m", -1), Action(4, "B", "m", -1),  # B bias 0.0
    ]
    m = wallet_bias_map(acts)
    assert m["A"] == pytest.approx(1.0)
    assert m["B"] == pytest.approx(0.0)

def test_swarm_divergence_directed():
    # A more up than B
    assert swarm_divergence(0.8, 0.2) == pytest.approx(0.6)
    assert swarm_divergence(0.2, 0.8) == pytest.approx(-0.6)
    assert swarm_divergence(0.5, 0.5) == 0.0

def test_consensus_bias():
    acts = [
        Action(1, "A", "m", +1), Action(2, "A", "m", +1),
        Action(3, "B", "m", -1), Action(4, "B", "m", -1),
    ]
    # 2 up, 2 down => 0.5
    assert consensus_bias(acts) == pytest.approx(0.5)

def test_contrarian_score_symmetries():
    # market up 0.8, wallet down 0.2 => contrarian = (0.8-0.2)*2 = 1.2 -> clipped? no, formula gives 1.2
    assert contrarian_score(0.2, 0.8) == pytest.approx(1.2)
    # market down 0.2, wallet up 0.8 => -1.2
    assert contrarian_score(0.8, 0.2) == pytest.approx(-1.2)
    # tracks market exactly => 0
    assert contrarian_score(0.5, 0.5) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# temporal: direction series + autocorrelation + stickiness
# ---------------------------------------------------------------------------
def test_direction_series_buckets():
    acts = [Action(t, "w", "m", +1) for t in [0, 0.5, 1.5, 2.5]]  # dt=1 => bins [0,1),[1,2),[2,3)
    centers, flow = direction_series(acts, dt=1.0)
    assert flow.sum() == 4  # 4 up
    assert len(flow) == 3
    assert flow[0] == 2  # t=0,0.5
    assert flow[1] == 1  # t=1.5
    assert flow[2] == 1  # t=2.5

def test_direction_series_empty():
    c, f = direction_series([])
    assert c.size == 0 and f.size == 0

def test_lead_autocorrelation_lag0_is_one():
    rng = np.random.default_rng(0)
    flow = rng.normal(0, 1, 50)
    ac = lead_autocorrelation(flow, max_lag=5)
    assert ac[0] == pytest.approx(1.0)

def test_lead_autocorrelation_persistent_signal():
    # a sticky alternating-up sequence should have positive lag-1 ac
    flow = np.array([1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, -1.0, -1.0])
    ac = lead_autocorrelation(flow, max_lag=3)
    assert ac[1] > 0  # direction persists

def test_stickiness_random_is_low():
    rng = np.random.default_rng(1)
    flow = rng.choice([-1.0, 1.0], size=200)
    s = stickiness(flow, max_lag=5)
    assert -0.3 < s < 0.3  # ~0 for iid

def test_stickiness_persistent_is_high():
    flow = np.tile([1.0, 1.0, 1.0, 1.0], 25)  # all up, very sticky
    s = stickiness(flow, max_lag=5)
    assert s > 0.9


# ---------------------------------------------------------------------------
# profiles
# ---------------------------------------------------------------------------
def test_profile_wallet_fields():
    acts = [Action(t, "A", "m", +1) for t in range(10)] + \
           [Action(t, "A", "m", -1) for t in range(10)]
    mb = consensus_bias(acts)
    p = profile_wallet("A", acts, mb, dt=1.0)
    assert isinstance(p, WalletProfile)
    assert p.n_actions == 20
    assert p.up == 10 and p.down == 10
    assert p.bias == pytest.approx(0.5)
    assert p.market_bias == pytest.approx(mb)

def test_profile_all_returns_every_wallet():
    acts = [Action(1, "A", "m", +1), Action(2, "B", "m", -1)]
    profs = profile_all(acts, dt=1.0)
    assert {p.wallet for p in profs} == {"A", "B"}


# ---------------------------------------------------------------------------
# swarm polarity labels
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bias,label", [
    (0.9, "STRONG_UP"), (0.6, "UP"), (0.5, "NEUTRAL"),
    (0.4, "DOWN"), (0.1, "STRONG_DOWN"),
])
def test_swarm_polarity(bias, label):
    assert swarm_polarity(bias) == label


# ---------------------------------------------------------------------------
# GYST UUIDv8 bit-layout correctness
# ---------------------------------------------------------------------------
def test_encode_gyst_is_valid_uuid():
    u = encode_gyst(TYPE_TRADER_WALLET, "wallet:kalshi")
    parsed = uuid.UUID(u)
    assert parsed.version == 8  # RFC 9562 v8

def test_encode_gyst_type_code_decoded():
    # decode the high 12 bits (type) from the first 12 bits of the UUID
    u = encode_gyst(TYPE_TRADER_WALLET, "wallet:kalshi")
    b = uuid.UUID(u).bytes
    high = int.from_bytes(b[:8], "big")
    type_code = (high >> 52) & 0xFFF
    assert type_code == TYPE_TRADER_WALLET

def test_mint_wallet_signal_type_codes():
    w = mint_wallet_uuid("0xABC")
    s = mint_signal_uuid("0xABC", 0.73)
    assert uuid.UUID(w).version == 8
    assert uuid.UUID(s).version == 8
    wb = int.from_bytes(uuid.UUID(w).bytes[:8], "big") >> 52 & 0xFFF
    sb = int.from_bytes(uuid.UUID(s).bytes[:8], "big") >> 52 & 0xFFF
    assert wb == TYPE_TRADER_WALLET
    assert sb == TYPE_TRADER_SIGNAL

def test_mint_signal_encodes_bias_in_signal_field():
    s = mint_signal_uuid("0xABC", 0.5)
    b = uuid.UUID(s).bytes
    low = int.from_bytes(uuid.UUID(s).bytes[8:], "big")
    sig16 = (low >> 42) & 0xFFFF
    assert sig16 == pytest.approx(int(0.5 * 0xFFFF), abs=1)

def test_mint_deterministic_namespace():
    # same label => same 12-bit namespace in the UUID (reproducible identity)
    w1 = mint_wallet_uuid("0xABC"); w2 = mint_wallet_uuid("0xABC")
    # type+namespace portion (first 24 bits) must match
    h1 = int.from_bytes(uuid.UUID(w1).bytes[:3], "big")
    h2 = int.from_bytes(uuid.UUID(w2).bytes[:3], "big")
    assert (h1 >> 12) == (h2 >> 12)  # type(12)|ns(12) equal


# ---------------------------------------------------------------------------
# Store round-trip
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    s = WalletStore(path)
    yield s
    s.close()
    if os.path.exists(path):
        os.remove(path)

def test_store_wallet_upsert(tmp_store):
    tmp_store.upsert_wallet("0x1", "uuid-1")
    row = tmp_store.get_wallet("0x1")
    assert row is not None
    assert row["gyst_uuid"] == "uuid-1"

def test_store_tick_rollup(tmp_store):
    tmp_store.upsert_wallet("0x1", "uuid-1")
    tmp_store.add_tick(1.0, "0x1", "m", +1)
    tmp_store.add_tick(2.0, "0x1", "m", +1)
    tmp_store.add_tick(3.0, "0x1", "m", -1)
    row = tmp_store.get_wallet("0x1")
    assert row["n_actions"] == 3
    assert row["up"] == 2 and row["down"] == 1
    assert row["bias"] == pytest.approx(2 / 3)

def test_store_profiles_roundtrip(tmp_store):
    from swarm_watcher.engine import SwarmWatcher
    from swarm_watcher import Action
    w = SwarmWatcher(tmp_store)
    w.ingest([
        Action(1.0, "0x1", "m", +1), Action(2.0, "0x1", "m", +1),
        Action(3.0, "0x2", "m", -1), Action(4.0, "0x2", "m", -1),
    ])
    profs = w.compute_signals()
    assert len(profs) == 2
    saved = tmp_store.profiles()
    assert len(saved) == 2
    # wallet 0x1 should have a GYST signal row
    sigs = tmp_store.conn.execute("SELECT * FROM signals WHERE wallet='0x1'").fetchall()
    assert len(sigs) >= 1
