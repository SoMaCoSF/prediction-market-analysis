"""
swarm_watcher.gyst_codes
=========================

Port of the canonical SoMaCoSF GYST UUID v8 (v3.0.0) bit layout to Python,
so the swarm watcher can mint REAL substrate-compatible UUIDs for wallets
(type 0x3F0 TRADER_WALLET) and signals (type 0x3F2 TRADER_SIGNAL).

Layout (128 bits, RFC 9562 v8):
  type(12) | namespace(12) | timestamp(24) | version(4)=0x8
         | fractal(12) | variant(2)=0b10 | provenance(4) | signal(16) | random(42)

This mirrors app/api/lib/gyst.ts encodeGYST(). We do NOT import the TS file;
we reproduce the bit packing exactly. The namespace is FNV-1a 12-bit of a
label (same hash as the TS hashNamespace12).

Provenance codes (4 bits):
  SYSTEM=0, HUMAN=1, AGENT=2, CONTRACT=3, DAEMON=4, ORACLE=5, WALLET=6, SWARM=7
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
import uuid

# --- Type codes (from lib/gyst.ts registry) ---
TYPE_TRADER_WALLET = 0x3F0   # on-chain wallet identity
TYPE_TRADER_SIGNAL = 0x3F2   # derived signal from trader action

# --- Provenance (4 bits) ---
PROV_SYSTEM = 0
PROV_HUMAN = 1
PROV_AGENT = 2
PROV_CONTRACT = 3
PROV_DAEMON = 4
PROV_ORACLE = 5
PROV_WALLET = 6
PROV_SWARM = 7

MASK12 = 0xFFF
MASK24 = 0xFFFFFF
MASK4 = 0xF
MASK16 = 0xFFFF
MASK42 = (1 << 42) - 1


def fnv1a_12(label: str) -> int:
    """FNV-1a 12-bit namespace hash (identical to TS hashNamespace12)."""
    h = 0x811C9DC5
    for ch in label.encode("utf-8"):
        h ^= ch
        h = (h * 0x01000193) & 0xFFFFFFFF
    return ((h ^ ((h >> 12) & 0xFFF)) & 0xFFF)


def encode_gyst(
    type_code: int,
    namespace_label: str,
    *,
    timestamp: int | None = None,
    fractal_depth: int = 1,
    fractal_domain: int = 1,
    fractal_generation: int = 0,
    forecast_signal: float = 0.0,
    provenance: int = PROV_SWARM,
    content_key: str = "",
) -> str:
    """Pack the GYST v8 layout and return a canonical UUID string.

    signal is normalized to [0,1] then scaled to 16 bits.
    """
    ts = int(timestamp if timestamp is not None else time.time()) & MASK24
    ns = fnv1a_12(namespace_label)
    sig = max(0.0, min(1.0, forecast_signal))
    sig16 = int(sig * MASK16) & MASK16
    rnd = secrets.randbits(42) & MASK42
    fd = fractal_depth & MASK12
    prov = provenance & MASK4

    # High 64 bits (bytes 0-7): type(12)|namespace(12)|timestamp(24)|version(4)|fractal(12)
    #   version nibble at high bits 12-15 => byte6 high nibble => uuid.version == 8.
    #   fractal occupies high bits 0-11 (byte7), no collision with type/ns/ts/version.
    # Low 64 bits (bytes 8-15): variant(2)|provenance(4)|signal(16)|random(42)
    #   variant at low bits 62-63 => byte8 high 2 bits => RFC variant 0b10.
    high = (
        ((type_code & MASK12) << 52)
        | ((ns & MASK12) << 40)
        | ((ts & MASK24) << 16)
        | (0x8 << 12)            # RFC version nibble (byte6 high nibble)
        | (fd & MASK12)          # fractal at high bits 0-11
    ) & 0xFFFFFFFFFFFFFFFF

    low = (
        (0b10 << 62)             # RFC variant (10xx) at low bits 62-63
        | ((prov & MASK4) << 58)
        | ((sig16 & MASK16) << 42)
        | (rnd & MASK42)
    ) & 0xFFFFFFFFFFFFFFFF

    # Pack into 16 bytes big-endian, format as UUID
    b = high.to_bytes(8, "big") + low.to_bytes(8, "big")
    return str(uuid.UUID(bytes=b))


def mint_wallet_uuid(wallet: str, platform: str = "kalshi") -> str:
    """GYST 0x3F0 TRADER_WALLET identity for an on-chain/account wallet."""
    return encode_gyst(
        TYPE_TRADER_WALLET,
        namespace_label=f"wallet:{platform}",
        fractal_domain=0x1,  # MARKET domain
        forecast_signal=0.0,
        provenance=PROV_WALLET,
        content_key=wallet,
    )


def mint_signal_uuid(wallet: str, bias: float, platform: str = "kalshi") -> str:
    """GYST 0x3F2 TRADER_SIGNAL — the derived up/down swarm signal for a wallet.

    signal field = bias (up fraction) in [0,1].
    """
    return encode_gyst(
        TYPE_TRADER_SIGNAL,
        namespace_label=f"signal:{platform}",
        fractal_domain=0x1,
        forecast_signal=bias,
        provenance=PROV_SWARM,
        content_key=f"{wallet}:bias={bias:.4f}",
    )


def type_name(type_code: int) -> str:
    return {TYPE_TRADER_WALLET: "TRADER_WALLET", TYPE_TRADER_SIGNAL: "TRADER_SIGNAL"}.get(type_code, f"0x{type_code:X}")
