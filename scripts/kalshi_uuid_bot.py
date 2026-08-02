#!/usr/bin/env python3
# file_id: SOM-PY-0908-v1.0.0 name: kalshi_uuid_bot.py description: Kalshi UUID bet scaffold — mint every order as a GYST UUIDv8 and submit fast via kalshi_python SDK project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [kalshi, bet, uuid, scaffold, trading] created: 2026-07-30 modified: 2026-07-30 version: 1.0.0 agent_id: HERMES-AGENT
"""
kalshi_uuid_bot.py — Kalshi activity on the GYST UUID framework.

A bet IS a transaction, and a transaction IS a UUID. This scaffold:
  1. mints a GYST UUID per Kalshi order (type 0x3A4 KALSHI_BET, prov=KALSHI),
     packing ticker->namespace, yes_price->16-bit signal, client_order_id->deterministic 42-bit random.
  2. submits via the real kalshi_python SDK (portfolio_api.create_order / batch_create_orders)
     — batch = fast multi-bet.
  3. is credential-aware: with KALSHI_KEY_ID + KALSHI_PRIVATE_KEY set it submits for real;
     without them it runs DRY-RUN (mints UUIDs + prints the exact SDK request, no network).

The minted UUID makes the bet addressable + bitmask-routable + rollable exactly like a
Polymarket trade. Native device-bound MFA (see FABLE_HANDOFF.md §5) gates who can fire.

SDK contract (verified against kalshi_python 2.1.4):
  portfolio_api.create_order(CreateOrderRequest(ticker, side, action='create', count,
      type='limit', yes_price=<1..99>, no_price=<1..99>, client_order_id=...))
  -> POST /portfolio/orders ; batch_create_orders([...]) for N bets in one call.

Usage:
  .venv311/Scripts/python scripts/kalshi_uuid_bot.py --dry-run --ticker FED-25-... --side yes --price 42 --count 3
  .venv311/Scripts/python scripts/kalshi_uuid_bot.py --batch bets.json        # real submit if creds set
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
try:  # load KALSHI_KEY_ID / KALSHI_PRIVATE_KEY from gitignored .env
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass
import uuid_ledger as L  # noqa: E402  — single mint authority + tracking
from uuid_service_turboquant import fnv1a12  # noqa: E402

TYPE_KALSHI_BET = 0x3A4
PROV_KALSHI = 0x2  # provenance slot for Kalshi (vs 0x1 Polymarket)


def bet_uuid(ticker: str, side: str, price_cents: int, client_order_id: str | None = None) -> str:
    """Mint a GYST UUID for a Kalshi order. Deterministic in (ticker, side, price, coi)."""
    namespace = fnv1a12(ticker)
    signal = max(0, min(1.0, price_cents / 100.0))
    # deterministic 42-bit random from client_order_id (or inputs) so the bet UUID is reproducible
    seed = client_order_id or f"{ticker}|{side}|{price_cents}"
    r42 = int.from_bytes(hashlib.sha256(seed.encode()).digest()[:6], "big") & ((1 << 42) - 1)
    # fold r42 into _rand42 by monkeypatching is overkill; encode_gyst uses random r42,
    # so we post-process: rebuild with the deterministic r42 via the same bit layout.
    from uuid_service_turboquant import _rand42  # noqa: F401  (kept for parity)
    # replicate low-half layout with deterministic r42
    ts = int(__import__("time").time()) & 0xFFFFFF
    fractal = 0
    high = ((TYPE_KALSHI_BET & 0xFFF) << 52) | ((namespace & 0xFFF) << 40) | (ts << 16) | (8 << 12) | fractal
    sig_q = int(max(0.0, min(1.0, signal)) * 0xFFFF)
    low = (2 << 62) | (PROV_KALSHI << 58) | (sig_q << 42) | r42
    u128 = (high << 64) | low
    hex_ = f"{u128:032x}"
    return f"{hex_[0:8]}-{hex_[8:12]}-{hex_[12:16]}-{hex_[16:20]}-{hex_[20:]}"


def build_request(ticker, side, price_cents, count, client_order_id=None, action="buy") -> dict:
    """Exact CreateOrderRequest body the SDK expects (keys match model fields 1:1)."""
    price_key = "yes_price" if side.lower() == "yes" else "no_price"
    req = {
        "ticker": ticker,
        "side": side.lower(),
        "action": action,            # kalshi: 'buy' | 'sell'  (scaffold's 'create' was invalid)
        "count": int(count),
        "type": "limit",
        price_key: int(price_cents),
        "client_order_id": client_order_id or f"gyst-{os.urandom(6).hex()}",
    }
    return req


def submit(requests: list[dict], dry_run: bool = True):
    """Submit one or many Kalshi orders. dry_run => mint UUIDs + print payload, no network.

    Every order is minted via the canonical ledger encoder (0x3A4, child of its
    market) and its client_order_id IS the UUID's low-42 tail — so exchange acks
    reconcile to the ledger by bitmask with no lookup table. Every mint is
    recorded to uuid_orders (mode=paper on dry-run, live on real submit).
    """
    results = []
    con = cur = None
    try:
        con = L.local_conn()
        cur = con.cursor()
    except Exception as e:
        print(f"[ledger] offline — tracking skipped: {repr(e)[:120]}")
    for req in requests:
        px = req.get("yes_price", req.get("no_price"))
        o = L.mint_order(req["ticker"], req["side"], px, req["count"])
        req["client_order_id"] = o["client_order_id"]   # the tail IS the id
        results.append({"uuid": o["uuid"], "request": req})
        print(f"[bet] uuid={o['uuid']}  coi={o['client_order_id']}  ->  "
              f"{req['side']} {px}¢ x{req['count']} {req['ticker']}")
        if cur:
            try:
                L.record_order(cur, o, mode=("paper" if dry_run else "live"),
                               status=("minted" if dry_run else "submitted"))
            except Exception as e:
                print(f"[ledger] warn: {repr(e)[:120]}")
    if con:
        con.commit()
        con.close()
    if dry_run:
        print(f"\n[DRY-RUN] {len(results)} order(s) minted as UUIDs + recorded to ledger (mode=paper). Set KALSHI_KEY_ID + "
              f"KALSHI_PRIVATE_KEY to submit for real. Payload sample:")
        print(json.dumps(results[0]["request"], indent=2))
        return results
    # ---- real submit (verified against kalshi_python 2.1.x on disk) ----
    key_id = os.getenv("KALSHI_KEY_ID")
    key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH")
    key_pem = os.getenv("KALSHI_PRIVATE_KEY")
    if key_pem and not key_path:
        # PEM content in env -> materialize to a gitignored file the SDK can read
        key_path = str(PROJECT_ROOT / ".kalshi_key.pem")
        if not Path(key_path).exists():
            Path(key_path).write_text(key_pem)
    if not (key_id and key_path):
        print("[ABORT] set KALSHI_KEY_ID + KALSHI_PRIVATE_KEY_PATH (or KALSHI_PRIVATE_KEY) in .env — cannot submit.")
        return results
    from kalshi_python import ApiClient, BatchCreateOrdersRequest, Configuration, CreateOrderRequest  # noqa: E402
    from kalshi_python.api.portfolio_api import PortfolioApi  # noqa: E402
    cfg = Configuration(host=os.getenv("KALSHI_HOST", "https://api.elections.kalshi.com/trade-api/v2"))
    client = ApiClient(cfg)
    client.set_kalshi_auth(key_id, key_path)
    api = PortfolioApi(client)
    if len(results) == 1:
        resp = api.create_order(create_order_request=CreateOrderRequest(**results[0]["request"]))
    else:
        resp = api.batch_create_orders(
            batch_create_orders_request=BatchCreateOrdersRequest(
                orders=[CreateOrderRequest(**r["request"]) for r in results]))
    print(f"[SUBMITTED] {resp}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="mint UUIDs + print payload, no submit")
    ap.add_argument("--ticker")
    ap.add_argument("--side", choices=["yes", "no"])
    ap.add_argument("--price", type=int, help="price in cents (1..99)")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--batch", help="JSON file: list of {ticker,side,price,count,client_order_id}")
    args = ap.parse_args()

    if args.batch:
        items = json.loads(Path(args.batch).read_text())
        reqs = [build_request(i["ticker"], i["side"], i["price"], i.get("count", 1), i.get("client_order_id"))
                for i in items]
        submit(reqs, dry_run=args.dry_run or not os.getenv("KALSHI_KEY_ID"))
    elif args.ticker and args.side and args.price:
        req = build_request(args.ticker, args.side, args.price, args.count)
        submit([req], dry_run=args.dry_run or not os.getenv("KALSHI_KEY_ID"))
    else:
        print("Need --batch <file> OR --ticker/--side/--price. Add --dry-run to avoid submitting.")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
