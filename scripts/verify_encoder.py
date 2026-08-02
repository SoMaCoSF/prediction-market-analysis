# file_id: SOM-PY-0914-v1.0.0 name: verify_encoder.py description: Determinism + round-trip verification for the GYST UUIDv8 encoder (uuid_service_turboquant). Reusable post-patch check. project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [verify, encoder, uuid, gyst] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""verify_encoder.py — prove the encoder is deterministic and decodes cleanly.

Checks:
  1. identical structured inputs -> identical UUID (low-42 content-addressed, never random)
  2. differing inputs -> differing UUIDs (no collisions on the seeds we vary)
  3. decode_gyst round-trips type / signal / provenance
  4. encode_poly_outcome_quote_uuid exists and round-trips (regression for the dead-code bug)

Usage:
  .venv311/Scripts/python scripts/verify_encoder.py
Exits 0 on ALL OK, 1 on any failure.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uuid_service_turboquant import (  # noqa: E402
    encode_gyst, decode_gyst,
    encode_poly_market_uuid, encode_poly_outcome_quote_uuid, encode_poly_trade_uuid,
)

fails = []


def check(name: str, ok: bool, detail: str = ""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not ok:
        fails.append(name)


# 1) determinism
a = encode_gyst(type_code=0x3A0, namespace=0x123, forecast_signal=0.5, provenance=0x2, timestamp_sec=12345)
b = encode_gyst(type_code=0x3A0, namespace=0x123, forecast_signal=0.5, provenance=0x2, timestamp_sec=12345)
check("deterministic identical inputs", a == b, f"{a} == {b}")

# 1b) determinism WITHOUT an explicit timestamp is not expected (ts=now changes),
#     but with same ts it must be identical. Also verify two rapid calls differ only by ts if clock ticks.
a2 = encode_gyst(type_code=0x3A0, namespace=0x123, forecast_signal=0.5, provenance=0x2)
b2 = encode_gyst(type_code=0x3A0, namespace=0x123, forecast_signal=0.5, provenance=0x2)
da, db = decode_gyst(a2), decode_gyst(b2)
check("same-second auto-ts identical", da.timestamp_sec == db.timestamp_sec and a2 == b2,
      f"ts {da.timestamp_sec} vs {db.timestamp_sec}")

# 2) differing inputs differ
c = encode_gyst(type_code=0x3A0, namespace=0x124, forecast_signal=0.5, provenance=0x2, timestamp_sec=12345)
check("different namespace -> different uuid", a != c)

# 3) round-trip
d = decode_gyst(a)
check("decode type == 0x3A0", d.type_code == 0x3A0, hex(d.type_code))
check("decode signal ~0.5", abs(d.signal_normalized - 0.5) < 1e-3, f"{d.signal_normalized:.6f}")
check("decode provenance == 0x2", d.provenance == 0x2, hex(d.provenance))
check("decode variant == 2", d.variant == 2, str(d.variant))
check("decode ts == 12345", d.timestamp_sec == 12345, str(d.timestamp_sec))

# 4) lattice helpers incl. the previously-dead quote fn
pm = encode_poly_market_uuid("trump-2028", 1.0, timestamp_sec=12345)
pq = encode_poly_outcome_quote_uuid("trump-2028", 0.17, timestamp_sec=12345)
pt = encode_poly_trade_uuid("trade-9", 0.55, market_uuid=pm, timestamp_sec=12345)
check("market type 0x3A0", decode_gyst(pm).type_code == 0x3A0)
check("quote type 0x3A1", decode_gyst(pq).type_code == 0x3A1)
check("trade type 0x3A2", decode_gyst(pt).type_code == 0x3A2)
check("quote signal ~0.17", abs(decode_gyst(pq).signal_normalized - 0.17) < 1e-3,
      f"{decode_gyst(pq).signal_normalized:.6f}")
check("trade signal ~0.55", abs(decode_gyst(pt).signal_normalized - 0.55) < 1e-3,
      f"{decode_gyst(pt).signal_normalized:.6f}")
check("trade fractal_depth == 1", decode_gyst(pt).fractal_depth == 1)

print()
if fails:
    print(f"RESULT: {len(fails)} FAILURE(S): {fails}")
    sys.exit(1)
print("RESULT: ALL OK — encoder deterministic + decodable")
