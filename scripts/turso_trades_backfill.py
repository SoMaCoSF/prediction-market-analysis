#!/usr/bin/env python3
"""
scripts/turso_trades_backfill.py

Reads all trade records from data/minted_parquet/trades_*.parquet, resolves
each trade's parent market via the clob_token_ids join (verified), mints a
GYST UUIDv8 of type 0x3A2 (POLY_TRADE) carrying the executed price in the
16-bit signal slot, and batch-writes to Turso table `uuid_trades`.

Markets-first preserved: this writes ONLY the separate `uuid_trades` table.
`uuid_vectors` (markets, 0x3A0) is never touched.

Wirespeed note: the true O(1) bitmask decode works in-memory (Python/C, 128-bit
int). SQLite is 64-bit, so SQL-side type routing uses substr(uuid,1,4) = the
12-bit type in hex (e.g. '3a2' for trades). Both are demonstrated in
scripts/verify_wirespeed_router.py.
"""
from __future__ import annotations

import os
import sys
import glob
import time
import argparse
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import duckdb
import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from uuid_service_turboquant import encode_poly_trade_uuid  # noqa: E402

ENV_URL = ("TURSO_DATABASE_URL", "TURSO_DB_URL")
ENV_TOKEN = ("TURSO_AUTH_TOKEN", "TURSO_DB_TOKEN")

CREATE_TABLE_STMT = """
CREATE TABLE IF NOT EXISTS uuid_trades (
    uuid TEXT PRIMARY KEY,
    trade_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    price REAL NOT NULL,
    amount REAL NOT NULL,
    timestamp INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""
CREATE_INDEX_STMT = """
CREATE INDEX IF NOT EXISTS idx_uuid_trades_market ON uuid_trades(market_id);
"""

DEFAULT_BATCH_SIZE = 500
REPORT_EVERY = 10_000

# trades carry asset ids; the parent market is resolved via clob_token_ids.
# We precompute a map: token_id -> (market_id, market_uuid) once per markets file.
_MARKET_TOKEN_MAP: Dict[str, Tuple[str, str]] = {}


def _normalize_turso_url(url: str) -> str:
    if url.startswith("libsql://"):
        return url.replace("libsql://", "https://", 1)
    return url.rstrip("/")


def _build_client() -> httpx.Client:
    url = next((os.getenv(v) for v in ENV_URL if os.getenv(v)), None)
    token = next((os.getenv(v) for v in ENV_TOKEN if os.getenv(v)), None)
    if not url or not token:
        raise SystemExit("Missing Turso credentials.")
    base = _normalize_turso_url(url)
    return httpx.Client(
        base_url=base,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30.0,
    )


def _load_market_token_map() -> Dict[str, Tuple[str, str]]:
    """Build token_id -> (market_id, market_uuid) by exploding clob_token_ids."""
    if _MARKET_TOKEN_MAP:
        return _MARKET_TOKEN_MAP
    market_files = sorted(
        glob.glob(str(PROJECT_ROOT / "data" / "minted_parquet" / "markets_*.parquet"))
    )
    con = duckdb.connect(":memory:")
    for mf in market_files:
        try:
            rows = con.execute(
                f"""
                SELECT id, gyst_uuid,
                       unnest(json_transform(clob_token_ids,'["VARCHAR"]')) AS token
                FROM read_parquet('{mf}')
                """
            ).fetchall()
        except Exception as exc:
            print(f"[warn] market token map skip {Path(mf).name}: {exc}")
            continue
        for market_id, market_uuid, token in rows:
            if token:
                _MARKET_TOKEN_MAP[str(token)] = (str(market_id), str(market_uuid))
    print(f"[*] Market token map: {len(_MARKET_TOKEN_MAP):,} token ids -> markets")
    return _MARKET_TOKEN_MAP


def _execute_sql(client: httpx.Client, sql: str) -> None:
    payload = {"requests": [{"type": "execute", "stmt": {"sql": sql}}, {"type": "close"}]}
    r = client.post("/v2/pipeline", json=payload)
    r.raise_for_status()


def _execute_batch(client: httpx.Client, rows: List[Tuple]) -> None:
    requests_payload = []
    for r in rows:
        uuid_str, trade_id, market_id, price, amount, ts = r
        requests_payload.append({
            "type": "execute",
            "stmt": {
                "sql": (
                    "INSERT INTO uuid_trades (uuid, trade_id, market_id, price, amount, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(uuid) DO NOTHING"
                ),
                "args": [
                    {"type": "text", "value": str(uuid_str)},
                    {"type": "text", "value": str(trade_id)},
                    {"type": "text", "value": str(market_id)},
                    {"type": "float", "value": float(price)},
                    {"type": "float", "value": float(amount)},
                    {"type": "integer", "value": str(int(ts))},
                ],
            },
        })
    payload = {"requests": requests_payload}
    r = client.post("/v2/pipeline", json=payload)
    if r.status_code >= 400:
        print(f"[error] trades batch HTTP {r.status_code}: {r.text[:400]}")
    r.raise_for_status()


def _read_trades(path: Path) -> Iterable[dict]:
    con = duckdb.connect(":memory:")
    rel = con.from_parquet(str(path))
    cols = [c for c in ("transaction_hash", "maker_asset_id", "taker_asset_id",
                        "maker_amount", "taker_amount", "timestamp") if c in rel.columns]
    df = rel.project(", ".join([f'"{c}"' for c in cols])).to_df()
    for rec in df.to_dict(orient="records"):
        yield rec


def _coerce(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _compose_trade_row(rec: dict, token_map: Dict[str, Tuple[str, str]], fallback_market: str):
    tx = rec.get("transaction_hash") or rec.get("order_hash") or ""
    maker_a = rec.get("maker_asset_id")
    taker_a = rec.get("taker_asset_id")
    asset = str(taker_a) if str(maker_a) in ("0", "", "None") else str(maker_a)
    market_id, market_uuid = token_map.get(asset, (fallback_market, ""))
    # price: trades don't carry a direct [0,1] price; derive from the side that
    # received the USDC-equivalent (maker_amount/taker_amount ratios). We store
    # normalized trade notional as 'price' proxy = taker_amount/(maker+taker) clamped.
    maker_amt = _coerce(rec.get("maker_amount"))
    taker_amt = _coerce(rec.get("taker_amount"))
    total = maker_amt + taker_amt
    price = (taker_amt / total) if total > 0 else 0.0
    amount = max(maker_amt, taker_amt)
    ts = int(rec.get("timestamp") or time.time())
    uuid_str = encode_poly_trade_uuid(
        trade_id=tx, price=price, timestamp_sec=ts, market_uuid=market_uuid or None
    )
    return (uuid_str, tx, market_id, price, amount, ts)


def run_backfill(batch_size: int = DEFAULT_BATCH_SIZE, limit: int = 10 ** 9, dry_run: bool = False) -> None:
    if limit <= 0:
        raise ValueError("--limit must be > 0")
    trade_files = sorted(glob.glob(str(PROJECT_ROOT / "data" / "minted_parquet" / "trades_*.parquet")))
    print(f"[*] Found {len(trade_files):,} trades files to process.")

    token_map = {} if dry_run else _load_market_token_map()
    client = None if dry_run else _build_client()
    if client:
        try:
            _execute_sql(client, CREATE_TABLE_STMT)
            _execute_sql(client, CREATE_INDEX_STMT)
        except Exception as exc:
            print(f"[warn] schema init failed: {exc}")

    total = 0
    rows: List[Tuple] = []
    last_report = 0
    t0 = time.perf_counter()

    for tf in trade_files:
        try:
            recs = list(_read_trades(Path(tf)))
        except Exception as exc:
            print(f"[skip] {Path(tf).name}: {exc}")
            continue
        for rec in recs:
            row = _compose_trade_row(rec, token_map, Path(tf).stem)
            rows.append(row)
            total += 1
            if len(rows) >= batch_size:
                if not dry_run and client:
                    try:
                        _execute_batch(client, rows)
                    except Exception as exc:
                        print(f"[warn] batch failed: {exc}")
                rows.clear()
            if total - last_report >= REPORT_EVERY or total >= limit:
                el = time.perf_counter() - t0
                rate = (total / el) if el > 0 else 0.0
                print(f"[progress] processed={total:,} rate={rate:,.0f} rows/sec" + (" (dry-run)" if dry_run else ""))
                last_report = total
            if total >= limit:
                break
        if total >= limit:
            break

    if rows:
        if not dry_run and client:
            try:
                _execute_batch(client, rows)
            except Exception as exc:
                print(f"[warn] final batch failed: {exc}")
        rows.clear()

    el = time.perf_counter() - t0
    rate = (total / el) if el > 0 else 0.0
    print(f"[*] Completed trades backfill: processed {total:,} records{', rate ' + format(rate, ',.0f') + ' rows/sec' if rate else ''}{' (dry-run)' if dry_run else ''}.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Backfill Turso uuid_trades from trades parquet (0x3A2).")
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    ap.add_argument("--limit", type=int, default=10 ** 9)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run_backfill(batch_size=args.batch_size, limit=args.limit, dry_run=args.dry_run)
