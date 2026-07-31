#!/usr/bin/env python3
# file_id: SOM-PY-0910-v1.0.0 name: pipe_a_to_b.py description: Build B from A: derive compliant GYST spawn-model tables from flat uuid_trades (A untouched, idempotent pipe) project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [pipe, spawn, compliance, migration] created: 2026-07-30 modified: 2026-07-30 version: 1.0.0 agent_id: HERMES-AGENT
"""
pipe_a_to_b.py — build the compliant spawn-model (B) FROM the flat table (A).

A = uuid_trades (flat, joined by string market_id, os.urandom random)  [NEVER MODIFIED]
B = uuid_markets (0x3A0) + uuid_quotes (0x3A1) + uuid_trades_b (0x3A2, parent_uuid)

For every row in A we:
  - resolve parent market UUID via encode_poly_market_uuid(market_id)  (0x3A0)
  - mint a COMPLIANT 0x3A2 trade UUID: deterministic random (sha256 of inputs),
    fractalDomain = MARKET (0x1), fractal_depth = 1, parent_uuid set
  - emit a 0x3A1 quote UUID for the price observation (depth=1, domain=MARKET)
B is idempotent: re-running replaces B from A (TRUNCATE B first). A is the audit ledger.

Compliance fixes applied (vs research spec v2.0.0):
  - random = sha256(namespace|signal|ts|trade_id)[:42 bits]  -> content-addressed (dedup by physics)
  - fractalDomain = 0x1 (MARKET) explicitly, not 0
  - parent_uuid links child to master (spawn tree, fractal spec sec 11)
"""
from __future__ import annotations
import os, sys, time, hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import psycopg2
from uuid_service_turboquant import encode_poly_market_uuid, fnv1a12  # noqa: E402

TYPE_MARKET = 0x3A0
TYPE_QUOTE = 0x3A1
TYPE_TRADE = 0x3A2
PROV_POLY = 0x1
DOMAIN_MARKET = 0x1


def det_random(*parts: str) -> int:
    """Deterministic 42-bit random from inputs (content-addressing)."""
    h = hashlib.sha256("|".join(parts).encode()).digest()
    return int.from_bytes(h[:6], "big") & ((1 << 42) - 1)


def to_signed(u128: int) -> tuple[int, int]:
    """Split 128-bit int into two signed BIGINT (hi, lo) for Postgres storage."""
    hi = (u128 >> 64) & 0xFFFFFFFFFFFFFFFF
    lo = u128 & 0xFFFFFFFFFFFFFFFF
    if hi >= 2**63:
        hi -= 2**64
    if lo >= 2**63:
        lo -= 2**64
    return hi, lo


def mint_trade_uuid(old_uuid: str, market_id: str, trade_id: str, ts: int, price: float):
    ns = fnv1a12(market_id)
    signal = max(0.0, min(1.0, price / 100.0)) if price else 0.0
    t24 = ts & 0xFFFFFF
    fractal = ((1 & 0xF) << 8) | ((DOMAIN_MARKET & 0xF) << 4) | (0 & 0xF)
    high = ((TYPE_TRADE & 0xFFF) << 52) | ((ns & 0xFFF) << 40) | (t24 << 16) | (8 << 12) | fractal
    sig_q = int(max(0.0, min(1.0, signal)) * 0xFFFF)
    r42 = det_random(old_uuid, market_id, trade_id, str(ts), str(price))
    low = (2 << 62) | (PROV_POLY << 58) | (sig_q << 42) | r42
    u128 = (high << 64) | low
    hx = f"{u128:032x}"
    return f"{hx[0:8]}-{hx[8:12]}-{hx[12:16]}-{hx[16:20]}-{hx[20:]}", to_signed(u128)


def mint_quote_uuid(old_uuid: str, market_id: str, ts: int, price: float):
    ns = fnv1a12(market_id)
    signal = max(0.0, min(1.0, price / 100.0)) if price else 0.0
    t24 = ts & 0xFFFFFF
    fractal = ((1 & 0xF) << 8) | ((DOMAIN_MARKET & 0xF) << 4) | (0 & 0xF)
    high = ((TYPE_QUOTE & 0xFFF) << 52) | ((ns & 0xFFF) << 40) | (t24 << 16) | (8 << 12) | fractal
    sig_q = int(max(0.0, min(1.0, signal)) * 0xFFFF)
    r42 = det_random(old_uuid, market_id, "quote", str(ts), str(price))
    low = (2 << 62) | (PROV_POLY << 58) | (sig_q << 42) | r42
    u128 = (high << 64) | low
    hx = f"{u128:032x}"
    return f"{hx[0:8]}-{hx[8:12]}-{hx[12:16]}-{hx[16:20]}-{hx[20:]}", to_signed(u128)


def run(batch: int = 200_000):
    t0 = time.perf_counter()
    con = psycopg2.connect(host="127.0.0.1", port=5432, dbname="postgres",
                           user="postgres", password="hermes_pg_2026", connect_timeout=10)
    con.autocommit = False
    cur = con.cursor()
    # ensure B schema (idempotent)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS uuid_markets (
            uuid TEXT PRIMARY KEY, market_id TEXT NOT NULL, uuid_hi BIGINT, uuid_lo BIGINT,
            created_at TIMESTAMPTZ DEFAULT now());
        CREATE TABLE IF NOT EXISTS uuid_trades_b (
            uuid TEXT PRIMARY KEY, uuid_hi BIGINT NOT NULL, uuid_lo BIGINT NOT NULL,
            trade_id TEXT NOT NULL, market_id TEXT NOT NULL, parent_uuid TEXT NOT NULL,
            price REAL, amount REAL, ts INTEGER, created_at TIMESTAMPTZ DEFAULT now());
        CREATE TABLE IF NOT EXISTS uuid_quotes (
            uuid TEXT PRIMARY KEY, uuid_hi BIGINT NOT NULL, uuid_lo BIGINT NOT NULL,
            market_id TEXT NOT NULL, parent_uuid TEXT NOT NULL,
            price REAL, ts INTEGER, created_at TIMESTAMPTZ DEFAULT now());
        CREATE INDEX IF NOT EXISTS idx_trades_b_parent ON uuid_trades_b (parent_uuid);
        CREATE INDEX IF NOT EXISTS idx_trades_b_type ON uuid_trades_b (((uuid_hi>>52)&4095));
        CREATE INDEX IF NOT EXISTS idx_quotes_parent ON uuid_quotes (parent_uuid);
    """)
    con.commit()
    # truncate B for idempotent rebuild from A
    cur.execute("TRUNCATE uuid_trades_b, uuid_quotes, uuid_markets;")
    con.commit()

    # stream A via ctid cursor (physical order, stable forward scan)
    from psycopg2.extras import execute_values
    last_ctid = None
    done = 0
    total = None
    cur.execute("SELECT count(*) FROM uuid_trades")
    total = cur.fetchone()[0]
    while True:
        if last_ctid is None:
            cur.execute(
                "SELECT ctid, uuid, trade_id, market_id, price, amount, ts FROM uuid_trades "
                "ORDER BY ctid LIMIT %s", (batch,))
        else:
            cur.execute(
                "SELECT ctid, uuid, trade_id, market_id, price, amount, ts FROM uuid_trades "
                "WHERE ctid > %s ORDER BY ctid LIMIT %s", (last_ctid, batch))
        rows = cur.fetchall()
        if not rows:
            break
        last_ctid = rows[-1][0]
        trade_rows, quote_rows, market_rows = [], [], []
        seen_markets = set()
        for _ctid, _old_uuid, trade_id, market_id, price, amount, ts in rows:
            parent, (phi, plo) = encode_poly_market_uuid(market_id), to_signed(
                int(encode_poly_market_uuid(market_id).replace("-", ""), 16))
            if market_id not in seen_markets:
                seen_markets.add(market_id)
                market_rows.append((parent, market_id, phi, plo))
            tu, (thi, tlo) = mint_trade_uuid(_old_uuid, market_id, trade_id, ts, price)
            trade_rows.append((tu, thi, tlo, trade_id, market_id, parent, price, amount, ts))
            qu, (qhi, qlo) = mint_quote_uuid(_old_uuid, market_id, ts, price)
            quote_rows.append((qu, qhi, qlo, market_id, parent, price, ts))
        execute_values(cur,
            "INSERT INTO uuid_markets (uuid, market_id, uuid_hi, uuid_lo) VALUES %s "
            "ON CONFLICT (uuid) DO NOTHING", market_rows)
        execute_values(cur,
            "INSERT INTO uuid_trades_b (uuid, uuid_hi, uuid_lo, trade_id, market_id, parent_uuid, price, amount, ts) "
            "VALUES %s", trade_rows)
        execute_values(cur,
            "INSERT INTO uuid_quotes (uuid, uuid_hi, uuid_lo, market_id, parent_uuid, price, ts) VALUES %s",
            quote_rows)
        con.commit()
        done += len(rows)
        print(f"[pipe A->B] {done:,}/{total:,}  ({time.perf_counter()-t0:.0f}s)", flush=True)
    # verify B counts
    cur.execute("SELECT count(*) FROM uuid_trades_b")
    bt = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM uuid_quotes")
    bq = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM uuid_markets")
    bm = cur.fetchone()[0]
    print(f"[pipe A->B] DONE. B: markets={bm:,} trades={bt:,} quotes={bq:,}  ({time.perf_counter()-t0:.0f}s)")
    con.close()


if __name__ == "__main__":
    run()
