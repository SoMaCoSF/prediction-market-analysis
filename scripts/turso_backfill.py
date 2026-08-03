#!/usr/bin/env python3
"""
scripts/turso_backfill.py
Reads `data/minted_parquet/*.parquet`, mints GYST UUIDv8 IDs with
`encode_poly_market_uuid`, and batch-inserts into Turso `uuid_vectors`.

Idempotent: INSERT ... ON CONFLICT(uuid) DO NOTHING.
Transactions: 500 rows per batch by default.
Progress: rate + count every 10,000 records.
"""

import argparse
import csv
import glob
import os
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any, List, Tuple

import duckdb
import httpx
import pandas as pd
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from uuid_service_turboquant import (
    PROV_POLY_MAKER,
    encode_poly_market_uuid,
)

ENV_VARS_URL = ("TURSO_DATABASE_URL", "TURSO_DB_URL")
ENV_VARS_TOKEN = ("TURSO_AUTH_TOKEN", "TURSO_DB_TOKEN")

CREATE_TABLE_STMT = """
CREATE TABLE IF NOT EXISTS uuid_vectors (
    uuid TEXT PRIMARY KEY,
    market_id TEXT NOT NULL,
    venue_id INTEGER NOT NULL,
    signal REAL NOT NULL,
    provenance INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""
CREATE_INDEX_STMT = """
CREATE INDEX IF NOT EXISTS idx_uuid_vectors_market ON uuid_vectors(market_id);
"""

INSERT_SQL = (
    "INSERT INTO uuid_vectors "
    "(uuid, market_id, venue_id, signal, provenance, timestamp) "
    "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(uuid) DO NOTHING"
)
DEFAULT_BATCH_SIZE = 500
REPORT_EVERY = 10_000
SAMPLE_CSV = PROJECT_ROOT / "data" / ".dry_run_sample.csv"


def _normalize_turso_url(url: str) -> str:
    if url.startswith("libsql://"):
        return url.replace("libsql://", "https://", 1)
    return url.rstrip("/")


def _build_client() -> httpx.Client:
    url = next((os.getenv(v) for v in ENV_VARS_URL if os.getenv(v)), None)
    token = next((os.getenv(v) for v in ENV_VARS_TOKEN if os.getenv(v)), None)
    if not url or not token:
        raise SystemExit("Missing Turso credentials: set TURSO_DATABASE_URL/TURSO_AUTH_TOKEN or TURSO_DB_URL/TURSO_DB_TOKEN.")
    base = _normalize_turso_url(url)
    return httpx.Client(
        base_url=base,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )


def _load_env() -> None:
    for name in (".env", ".env.local", ".env_turso"):
        fp = PROJECT_ROOT / name
        if not fp.exists():
            continue
        try:
            import dotenv
            dotenv.load_dotenv(fp, override=False)
            return
        except Exception:
            pass
        try:
            with fp.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("\"'")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass


def _execute_sql(client: httpx.Client, sql: str, args: List[Any] | None = None) -> dict:
    statements: List[dict] = [{"sql": sql}]
    if args:
        statements[0]["args"] = [
            {"type": "text", "value": str(a)} if isinstance(a, str)
            else {"type": "integer", "value": str(int(a))} if isinstance(a, int)
            else {"type": "float", "value": float(a)} if isinstance(a, float)
            else {"type": "text", "value": str(a)}
            for a in args
        ]
    payload = {"requests": [{"type": "execute", "stmt": s} for s in statements]}
    response = client.post("/v2/pipeline", json=payload)
    response.raise_for_status()
    return response.json()


def _execute_batch(client: httpx.Client, rows: List[Tuple[str, str, int, float, int, int]]) -> None:
    requests_payload = []
    for row in rows:
        uuid_str, market_id, venue_id, signal, provenance, timestamp = row
        requests_payload.append({
            "type": "execute",
            "stmt": {
                "sql": INSERT_SQL,
                "args": [
                    {"type": "text", "value": uuid_str},
                    {"type": "text", "value": market_id},
                    {"type": "integer", "value": str(int(venue_id))},
                    {"type": "float", "value": float(signal)},
                    {"type": "integer", "value": str(int(provenance))},
                    {"type": "integer", "value": str(int(timestamp))},
                ],
            },
        })
    payload = {"requests": requests_payload}
    response = client.post("/v2/pipeline", json=payload)
    if response.status_code >= 400:
        print(f"[error] batch insert HTTP {response.status_code}: {response.text[:600]}")
    response.raise_for_status()
    _ = response.json()


def _read_parquet_records(path: Path) -> Iterable[dict]:
    con = duckdb.connect(":memory:")
    rel = con.from_parquet(str(path), binary_as_string=False)
    cols = [c for c in ("ticker", "market_id", "timestamp") if c in rel.columns]
    if not cols:
        cols = rel.columns
    df: pd.DataFrame = rel.project(", ".join([f'"{c}"' for c in cols])).to_df()
    for record in df.to_dict(orient="records"):
        yield record


def _coerce_timestamp(raw: Any) -> int:
    try:
        value = int(raw)
    except Exception:
        value = int(time.time())
    return value if value > 0 else int(time.time())


def _compose_row(record: dict, fallback_market_id: str) -> Tuple[str, str, int, float, int, int]:
    # Prefer the real market identifier from the parquet (markets files carry
    # slug/id; trades files carry none and are skipped upstream).
    market_id = (
        record.get("slug")
        or record.get("id")
        or record.get("ticker")
        or record.get("market_id")
        or fallback_market_id
    )
    market_id = str(market_id)
    timestamp = _coerce_timestamp(record.get("timestamp", int(time.time())))
    # Use the row's precomputed GYST UUID when present (markets parquet already
    # has one); otherwise mint from the real market_id.
    uuid_str = record.get("gyst_uuid") or encode_poly_market_uuid(
        market_id=market_id, confidence=1.0, timestamp_sec=timestamp
    )
    return str(uuid_str), market_id, 200, 1.0, PROV_POLY_MAKER, timestamp


def _write_dry_run_csv(sample_rows: List[Tuple[str, str, int, float, int, int]]) -> None:
    SAMPLE_CSV.parent.mkdir(parents=True, exist_ok=True)
    with SAMPLE_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["uuid", "market_id", "venue_id", "signal", "provenance", "timestamp"])
        writer.writerows(sample_rows)


def run_backfill(batch_size: int = DEFAULT_BATCH_SIZE, limit: int = 10 ** 9, dry_run: bool = False) -> None:
    if limit <= 0:
        raise ValueError("--limit must be > 0")

    parquet_files = sorted(glob.glob(str(PROJECT_ROOT / "data" / "minted_parquet" / "*.parquet")))
    print(f"[*] Found {len(parquet_files)} parquet files to process.")

    client = None if dry_run else _build_client()
    if client:
        try:
            _execute_sql(client, CREATE_TABLE_STMT)
            _execute_sql(client, CREATE_INDEX_STMT)
        except Exception as exc:
            print(f"[warn] schema init via HTTP pipeline failed: {exc}")

    total_processed = 0
    rows: List[Tuple[str, str, int, float, int, int]] = []
    sample_rows: List[Tuple[str, str, int, float, int, int]] = []
    last_report = 0
    t0 = time.perf_counter()

    pbar = tqdm(total=limit, desc="minted", unit="row", dynamic_ncols=True)

    try:
        for p_file in parquet_files:
            try:
                records = list(_read_parquet_records(Path(p_file)))
            except Exception as exc:
                print(f"[skip] {p_file}: {exc}")
                continue

            # Auto-prioritize markets: skip files that carry no market-id column
            # (e.g. trades_* with only block/tx/maker/taker — cannot be tied to a market).
            if records:
                keys = set(records[0].keys())
                if not (keys & {"gyst_uuid", "id", "slug", "ticker", "market_id"}):
                    print(f"[skip] {Path(p_file).name}: no market-id columns (trades file)")
                    continue

            for record in records:
                row = _compose_row(record, Path(p_file).stem)
                if len(sample_rows) < 50:
                    sample_rows.append(row)
                rows.append(row)
                total_processed += 1

                if len(rows) >= batch_size:
                    if not dry_run and client:
                        try:
                            _execute_batch(client, rows)
                        except Exception as exc:
                            print(f"[warn] batch insert failed: {exc}")
                    rows.clear()

                if total_processed - last_report >= REPORT_EVERY or total_processed >= limit:
                    elapsed = time.perf_counter() - t0
                    rate = (total_processed / elapsed) if elapsed > 0 else 0.0
                    print(
                        f"[progress] processed={total_processed:,} rate={rate:,.0f} rows/sec"
                        + (" (dry-run)" if dry_run else "")
                    )
                    last_report = total_processed

                if total_processed >= limit:
                    break

            pbar.update(min(len(records), max(0, limit - pbar.n)))

            if total_processed >= limit:
                break

        if rows:
            if not dry_run and client:
                try:
                    _execute_batch(client, rows)
                except Exception as exc:
                    print(f"[warn] final batch insert failed: {exc}")
            rows.clear()
    finally:
        pbar.close()

    elapsed_total = time.perf_counter() - t0
    rate_total = (total_processed / elapsed_total) if elapsed_total > 0 else 0.0
    suffix = " (dry-run)" if dry_run else ""
    print(f"[*] Completed backfill: processed {total_processed:,} records{', rate ' + f'{rate_total:,.0f} rows/sec' if rate_total else ''}{suffix}.")

    if dry_run and sample_rows:
        _write_dry_run_csv(sample_rows)
        print(f"[dry-run] Sample CSV: {SAMPLE_CSV}")
        for row in sample_rows[: min(len(sample_rows), 5)]:
            print(f"        sample -> {row}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill Turso `uuid_vectors` from minted Parquet.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Batch insert size.")
    parser.add_argument("--limit", type=int, default=10 ** 9, help="Max rows to process.")
    parser.add_argument("--dry-run", action="store_true", help="Verify pipeline without modifying Turso.")
    args = parser.parse_args()

    _load_env()
    run_backfill(batch_size=args.batch_size, limit=args.limit, dry_run=args.dry_run)
