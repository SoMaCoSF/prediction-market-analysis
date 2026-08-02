"""
file_id: SOM-LIB-0001-v1.0.0
name: gyst.py
description: Unified Python implementation of GYST UUIDv8 Protocol + TurboQuant
             prediction market address bitfields. Mirrors gyst_uuid.ts exactly.
"""

from __future__ import annotations

import os
import time
import uuid
import hashlib
from typing import Optional, Dict, Any, Union


# ==============================================================================
# PROVENANCE CODES (4 bits: bits 60..63)
# ==============================================================================
PROV_UNKNOWN      = 0x0
PROV_DEXTER       = 0x1
PROV_CLI          = 0x2
PROV_CLAUDE       = 0x3
PROV_DASHBOARD    = 0x4
PROV_REGISTRY     = 0x5
PROV_AGENT        = 0x6
PROV_POLY_MAKER   = 0x7
PROV_POLY_TAKER   = 0x8
PROV_KALSHI       = 0x9
PROV_BACKFILL     = 0xA


class GYSTUUID:
    VERSION = 8
    VARIANT = 0b10  # RFC 9562 variant 2

    # Type Registry (12-bit, bits 116..127)
    TYPE_REGISTRY: Dict[int, str] = {
        0x011: "PopSoc_Event",
        0x014: "Vendor",
        0x015: "Product",
        0x102: "Registration_Ticket",
        0x3A0: "POLY_MARKET",
        0x3A1: "POLY_OUTCOME_QUOTE",
        0x3A2: "POLY_TRADE_EXECUTION",
        0x3B0: "KALSHI_MARKET",
        0x3B1: "KALSHI_QUOTE",
        0x3B2: "KALSHI_TRADE_EXECUTION",
        0x400: "Locus_Wallet",
        0x401: "Locus_Subwallet",
        0x402: "Locus_Transaction",
        0x403: "Locus_Escrow",
        0x404: "Locus_x402_Call",
        0x405: "Locus_Task_Fiverr",
        0x407: "Locus_Policy",
        0x409: "Locus_Settlement",
        0x40B: "Aerodrome_veLock",
        0x40C: "Aerodrome_GaugeVote",
        0x40D: "Aerodrome_PredictiveForecast",
        0x40E: "Aerodrome_RewardEpoch",
    }

    @staticmethod
    def fnv1a12(text: str) -> int:
        """Hash string down to a 12-bit namespace value (0..4095)."""
        h = 0x811C9DC5
        for byte in text.encode("utf-8"):
            h ^= byte
            h = (h * 0x01000193) & 0xFFFFFFFF
        # Fold 32-bit hash down to 12-bit
        return ((h >> 12) ^ (h & 0xFFF)) & 0xFFF

    @classmethod
    def generate(
        cls,
        identity_str: str,
        type_code: int,
        namespace: str = "default",
        custom_ts: Optional[int] = None,
        fractal_depth: int = 0,
        fractal_domain: int = 1,
        fractal_gen: int = 0,
        forecast_signal: Optional[float] = None,
        provenance: int = PROV_UNKNOWN,
    ) -> uuid.UUID:
        """
        Generate a RFC 9562 compliant 128-bit GYST UUIDv8.
        
        Bit layout (128 bits total):
          116..127: type_code (12 bit)
          104..115: namespace_hash (12 bit)
           80..103: custom timestamp / sequence (24 bit)
           76..79 : version = 8 (4 bit)
           64..75 : fractal topology field (12 bit)
           62..63 : variant = 0b10 (2 bit)
           60..61 : provenance / execution flags (2 bit low)
            0..59 : payload / quantization bits (60 bit)
        """
        ns_hash = cls.fnv1a12(f"{namespace}:{identity_str}") & 0xFFF
        
        # 24-bit timestamp (seconds or relative offset)
        ts_val = (custom_ts if custom_ts is not None else int(time.time())) & 0xFFFFFF
        
        # 12-bit Fractal topology (4-bit depth, 4-bit domain, 4-bit generation)
        fractal_val = ((fractal_depth & 0xF) << 8) | ((fractal_domain & 0xF) << 4) | (fractal_gen & 0xF)
        
        # Compute 60-bit payload (signal vector or hash entropy)
        if forecast_signal is not None:
            # Quantize probability float [0.0..1.0] into 16-bit int
            signal_q16 = int(max(0.0, min(1.0, forecast_signal)) * 65535) & 0xFFFF
            # Combine 16-bit probability + 4-bit provenance + 40-bit FNV hash entropy
            entropy = (int(hashlib.sha256(identity_str.encode()).hexdigest(), 16)) & 0xFFFFFFFFFF
            payload_60 = (signal_q16 << 44) | ((provenance & 0xF) << 40) | entropy
        else:
            payload_60 = (int(hashlib.sha256(identity_str.encode()).hexdigest(), 16)) & ((1 << 60) - 1)

        # Assemble full 128-bit integer
        i128 = (
            ((type_code & 0xFFF) << 116)
            | ((ns_hash & 0xFFF) << 104)
            | ((ts_val & 0xFFFFFF) << 80)
            | ((cls.VERSION & 0xF) << 76)
            | ((fractal_val & 0xFFF) << 64)
            | ((cls.VARIANT & 0x3) << 62)
            | (payload_60 & ((1 << 62) - 1))
        )

        return uuid.UUID(int=i128)

    @classmethod
    def parse(cls, u: Union[str, uuid.UUID]) -> Dict[str, Any]:
        """Parse a GYST UUID back into its structural bitfield components."""
        uuid_obj = u if isinstance(u, uuid.UUID) else uuid.UUID(u)
        val = uuid_obj.int

        type_code = (val >> 116) & 0xFFF
        forecast_q16 = (val >> 44) & 0xFFFF

        return {
            "type_code": hex(type_code),
            "type_name": cls.TYPE_REGISTRY.get(type_code, "Unknown"),
            "namespace_hash": (val >> 104) & 0xFFF,
            "timestamp": (val >> 80) & 0xFFFFFF,
            "version": (val >> 76) & 0xF,
            "fractal_topology": (val >> 64) & 0xFFF,
            "variant": (val >> 62) & 0x3,
            "forecast_signal": round(forecast_q16 / 65535.0, 4),
            "uuid_str": str(uuid_obj),
        }

# Domain Helper Shortcuts
def encode_poly_market_uuid(market_id: str, confidence: float = 1.0, timestamp_sec: Optional[int] = None) -> str:
    return str(GYSTUUID.generate(
        identity_str=market_id,
        type_code=0x3A0,
        namespace="polymarket",
        custom_ts=timestamp_sec,
        forecast_signal=confidence,
        provenance=PROV_POLY_MAKER
    ))

def encode_kalshi_market_uuid(ticker: str, confidence: float = 1.0, timestamp_sec: Optional[int] = None) -> str:
    return str(GYSTUUID.generate(
        identity_str=ticker,
        type_code=0x3B0,
        namespace="kalshi",
        custom_ts=timestamp_sec,
        forecast_signal=confidence,
        provenance=PROV_KALSHI
    ))