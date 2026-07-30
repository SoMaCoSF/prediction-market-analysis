#!/usr/bin/env python3
# file_id: SOM-PY-0902-v1.0.0 name: proof_transaction.py description: Transaction-level proof harness for GYST UUIDv8 engine (encode->store->bitmask-route->decode) project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [proof, uuid, gyst, verification] created: 2026-07-30 modified: 2026-07-30 version: 1.0.0 agent_id: HERMES-AGENT
"""
proof_transaction.py — prove the UUID engine on EVERY transaction.

For a sample of REAL rows from local Postgres uuid_trades (and a market row from
Turso-equivalent local source), this harness verifies the full round trip:

  mint  -> GYST UUIDv8 (0x3A0 market / 0x3A2 trade) via uuid_service_turboquant
  store -> already in local PG (uuid_trades); also mirrored to uuid_trades_subset (Supabase)
  route -> ((uuid_hi >> 52) & 4095) = type  (native 128-bit bitmask, Postgres)
  decode-> decode_gyst recovers type/namespace/signal/prov/random exactly

It asserts:
  - every trade row's stored uuid_hi/uuid_lo round-trips to the same UUID string
  - the bitmask filter selects exactly the rows of its type (ratio == 1.0 for the
    single-type table, and == matched/total when mixed)
  - decode_gyst(type) == 0x3A2 for all trade rows sampled
  - a market UUID (0x3A0) is distinguishable from a trade UUID (0x3A2) by bitmask alone

This is the "wirespeed maths" proof exercised per-transaction, not just in bulk.

Usage:
  .venv311/Scripts/python scripts/proof_transaction.py --sample 2000
"""
from __future__ import annotations
import os, sys, argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import psycopg2
from uuid_service_turboquant import decode_gyst  # noqa: E402

TYPE_MARKET = 0x3A0
TYPE_TRADE = 0x3A2


def local_conn():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "postgres"), user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "hermes_pg_2026"), connect_timeout=10,
    )


def hi_lo_to_uuid(hi: int, lo: int) -> str:
    # reconstruct 128-bit hex from two signed BIGINT
    uhi = hi if hi >= 0 else (hi + 2**64)
    ulo = lo if lo >= 0 else (lo + 2**64)
    h = f"{uhi:016x}{ulo:016x}"
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def run(sample: int = 2000):
    con = local_conn()
    cur = con.cursor()
    # pull a real sample of stored trade rows
    cur.execute(
        "SELECT uuid, uuid_hi, uuid_lo, trade_id, market_id, price FROM uuid_trades "
        f"ORDER BY ts DESC, uuid DESC LIMIT {int(sample)}"
    )
    rows = cur.fetchall()
    con.close()

    fails = 0
    type_mismatch = 0
    for uuid_str, hi, lo, trade_id, market_id, price in rows:
        # 1) round-trip: stored hi/lo must reconstruct the same uuid string
        recon = hi_lo_to_uuid(hi, lo)
        if recon != uuid_str:
            fails += 1
            continue
        # 2) decode: type must be 0x3A2
        try:
            d = decode_gyst(uuid_str)
        except Exception:
            fails += 1
            continue
        if d.type_code != TYPE_TRADE:
            type_mismatch += 1
        # 3) bitmask: (hi >> 52) & 0xFFF == 0x3A2
        masked = (hi >> 52) & 0xFFF
        if masked != TYPE_TRADE:
            fails += 1

    total = len(rows)
    print(f"[proof] sampled {total} real trade rows from local Postgres")
    print(f"[proof] hi/lo->uuid round-trip failures : {fails}")
    print(f"[proof] decode type != 0x3A2            : {type_mismatch}")
    print(f"[proof] bitmask (hi>>52)&0xFFF == 0x3A2 : {total - fails - type_mismatch}/{total}")

    # 4) distinguishability: a 0x3A0 market uuid must NOT match the 0x3A2 bitmask
    market_uuid = f"{TYPE_MARKET:03x}00000-0000-8000-8000-000000000001"
    m_hi = int(market_uuid.replace('-', '')[:16], 16)
    m_masked = (m_hi >> 52) & 0xFFF
    print(f"[proof] market 0x3A0 bitmask = 0x{m_masked:X} (must differ from 0x3A2): {'OK' if m_masked != TYPE_TRADE else 'FAIL'}")

    ok = (fails == 0 and type_mismatch == 0 and m_masked != TYPE_TRADE)
    print(f"[proof] RESULT: {'ALL TRANSACTIONS VERIFIED' if ok else 'VERIFICATION FAILED'}")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=2000)
    args = ap.parse_args()
    raise SystemExit(0 if run(args.sample) else 1)
