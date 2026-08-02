# file_id: SOM-PY-0916-v1.0.0 name: uuid_ledger.py description: UUID-native trading ledger — mint every order/fill/settlement as a GYST UUIDv8 child; reconcile exchange acks by low-42 bitmask (no lookup table); spawn-tree P&L project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [ledger, uuid, gyst, kalshi, trading, pnl] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""uuid_ledger.py — the trading ledger where every event IS a UUID.

Hierarchy (per the GYST spawn model):
  market (0x3B0, depth 0)
    -> order  (0x3A4, depth 1, namespace=fnv1a12(parent_uuid), gen++)
      -> fill (0x3A7, depth 2)
    -> mark/settle (0x3AA / 0x3A9, depth 1)

Reconciliation thesis (now TRUE by construction):
  client_order_id = hex(order UUID's low-42 tail). The exchange echoes it back
  on every ack/fill, so ANY ack resolves to its order with one bitmask:
      uuid_lo & (2^42 - 1) = int(client_order_id, 16)
  No lookup table. The ledger audits itself.

Determinism: order UUIDs are minted with content_seed = the order payload, so
re-minting the same logical order yields the same UUID (idempotent retry-safe),
while distinct orders can never collide (the old uuid_trades_b PK-collision bug).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from uuid_service_turboquant import decode_gyst, encode_gyst, fnv1a12  # noqa: E402

# ---- Trading type codes (single registry for the money path) ----
TYPE_KALSHI_MARKET = 0x3B0
TYPE_KALSHI_BET    = 0x3A4   # order BID (buy YES)
TYPE_KALSHI_ASK    = 0x3A5   # order ASK (sell YES / reduce)
TYPE_KALSHI_ACK    = 0x3A6   # exchange acknowledgment (child of order)
TYPE_KALSHI_FILL   = 0x3A7   # fill (child of order)
TYPE_KALSHI_SETTLE = 0x3A9   # settlement (child of market)
TYPE_KALSHI_MARK   = 0x3AA   # mark-to-market (child of market)
PROV_KALSHI        = 0x9

MASK42 = (1 << 42) - 1
TWO64  = 1 << 64


def to_signed64(v: int) -> int:
    """Unsigned 64-bit -> signed BIGINT storage form."""
    return v - TWO64 if v >= (1 << 63) else v


def hi_lo(uuid_str: str) -> tuple[int, int]:
    """UUID string -> (signed_hi, signed_lo) for BIGINT columns."""
    u = int(uuid_str.replace("-", ""), 16)
    return to_signed64(u >> 64), to_signed64(u & (TWO64 - 1))


def lo42(uuid_str: str) -> int:
    """The reconciliation key: low 42 bits of the UUID."""
    return int(uuid_str.replace("-", ""), 16) & MASK42


def mint_market_uuid(ticker: str, *, ts: int | None = None) -> str:
    """0x3B0 market root (depth 0)."""
    return encode_gyst(
        type_code=TYPE_KALSHI_MARKET, namespace=fnv1a12(f"kalshi:{ticker}"),
        timestamp_sec=ts, fractal_depth=0, fractal_domain=0x1,
        forecast_signal=1.0, provenance=PROV_KALSHI, content_seed=ticker,
    )


def mint_order(ticker: str, side: str, price_cents: int, count: int,
               *, parent_uuid: str | None = None, ts: int | None = None) -> dict:
    """Mint an order UUID as a child of its market.

    side 'yes' (buy YES) -> 0x3A4 ORDER_BID; side 'no' -> 0x3A5 ORDER_ASK, so the
    side is routable by the type bitmask alone. client_order_id = low-42 hex tail.
    Deterministic per logical order payload -> idempotent retries are safe.
    """
    parent = parent_uuid or mint_market_uuid(ticker, ts=ts)
    tc = TYPE_KALSHI_BET if side.lower() == "yes" else TYPE_KALSHI_ASK
    seed = f"order|{ticker}|{side}|{price_cents}|{count}|{ts or int(time.time())}"
    u = encode_gyst(
        type_code=tc, namespace=fnv1a12(parent),
        timestamp_sec=ts, fractal_depth=1, fractal_domain=0x1, fractal_generation=1,
        forecast_signal=price_cents / 100.0, provenance=PROV_KALSHI,
        content_seed=seed,
    )
    hi, lo = hi_lo(u)
    return {
        "uuid": u, "uuid_hi": hi, "uuid_lo": lo,
        "client_order_id": format(lo42(u), "x"),   # the tail IS the id
        "parent_uuid": parent, "ticker": ticker, "side": side,
        "price_cents": price_cents, "count": count,
        "ts": ts if ts is not None else int(time.time()),
    }


def mint_ack(order_uuid: str, exchange_order_id: str, avg_fill_price_cents: float | None,
             *, ts_ms: int | None = None) -> dict:
    """Mint an ACK UUID (0x3A6) as a child of its order.

    low-42 = content42(exchange_order_id) -> the exchange's own ack id reconciles
    to this UUID by the same bitmask. signal = average fill price when present.
    """
    d = decode_gyst(order_uuid)
    ts_sec = (ts_ms // 1000) if ts_ms else int(time.time())
    sig = (avg_fill_price_cents / 100.0) if avg_fill_price_cents is not None else d.signal_normalized
    u = encode_gyst(
        type_code=TYPE_KALSHI_ACK, namespace=d.namespace,
        timestamp_sec=ts_sec, fractal_depth=2, fractal_domain=d.fractal_domain,
        fractal_generation=d.fractal_generation + 1,
        forecast_signal=sig, provenance=PROV_KALSHI,
        content_seed=f"ack|{exchange_order_id}",
    )
    hi, lo = hi_lo(u)
    return {"uuid": u, "uuid_hi": hi, "uuid_lo": lo, "parent_uuid": order_uuid,
            "exchange_order_id": exchange_order_id, "ts": ts_sec}


def mint_fill(order_uuid: str, price_cents: int, count: int,
              *, ts: int | None = None, fill_seq: int = 0,
              exchange_fill_id: str | None = None) -> dict:
    """Mint a fill UUID (0x3A7) as a child of its order.

    When exchange_fill_id is given it becomes the content seed, so the exchange
    fill reconciles by the same low-42 bitmask."""
    d = decode_gyst(order_uuid)
    seed = (f"xf|{exchange_fill_id}" if exchange_fill_id
            else f"fill|{order_uuid}|{price_cents}|{count}|{fill_seq}|{ts or int(time.time())}")
    u = encode_gyst(
        type_code=TYPE_KALSHI_FILL, namespace=d.namespace,
        timestamp_sec=ts, fractal_depth=2, fractal_domain=d.fractal_domain,
        fractal_generation=d.fractal_generation + 1,
        forecast_signal=price_cents / 100.0, provenance=PROV_KALSHI,
        content_seed=seed,
    )
    hi, lo = hi_lo(u)
    return {"uuid": u, "uuid_hi": hi, "uuid_lo": lo, "parent_uuid": order_uuid,
            "price_cents": price_cents, "count": count,
            "ts": ts if ts is not None else int(time.time())}


def mint_mark(ticker: str, market_uuid: str, mark_cents: int, *,
              kind: str = "settle", ts: int | None = None) -> dict:
    """Mint a settlement/mark UUID (0x3A9/0x3AA) as a child of the market."""
    tc = TYPE_KALSHI_SETTLE if kind == "settle" else TYPE_KALSHI_MARK
    u = encode_gyst(
        type_code=tc, namespace=fnv1a12(market_uuid),
        timestamp_sec=ts, fractal_depth=1, fractal_domain=0x1, fractal_generation=1,
        forecast_signal=mark_cents / 100.0, provenance=PROV_KALSHI,
        content_seed=f"{kind}|{ticker}|{mark_cents}|{ts or int(time.time())}",
    )
    hi, lo = hi_lo(u)
    return {"uuid": u, "uuid_hi": hi, "uuid_lo": lo, "parent_uuid": market_uuid,
            "ticker": ticker, "mark_cents": mark_cents, "kind": kind,
            "ts": ts if ts is not None else int(time.time())}


# ---------------- DB layer (local Postgres) ----------------

def local_conn():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "postgres"), user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "hermes_pg_2026"), connect_timeout=10,
    )


def record_order(cur, o: dict, *, mode: str = "paper", status: str = "minted",
                 exchange_order_id: str | None = None):
    cur.execute(
        """INSERT INTO uuid_orders
           (uuid, uuid_hi, uuid_lo, client_order_id, parent_uuid, ticker, side,
            price_cents, count, status, mode, exchange_order_id, ts)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (uuid) DO NOTHING""",
        (o["uuid"], o["uuid_hi"], o["uuid_lo"], o["client_order_id"], o["parent_uuid"],
         o["ticker"], o["side"], o["price_cents"], o["count"], status, mode,
         exchange_order_id, o["ts"]))


def record_fill(cur, f: dict, *, fee_cents: int = 0, exchange_fill_id: str | None = None):
    cur.execute(
        """INSERT INTO uuid_fills (uuid, uuid_hi, uuid_lo, parent_uuid, price_cents, count, fee_cents, exchange_fill_id, ts)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (uuid) DO NOTHING""",
        (f["uuid"], f["uuid_hi"], f["uuid_lo"], f["parent_uuid"], f["price_cents"],
         f["count"], fee_cents, exchange_fill_id, f["ts"]))


def record_ack(cur, a: dict, *, fill_count: float = 0.0, remaining_count: float = 0.0,
               avg_price_cents: float | None = None):
    cur.execute(
        """INSERT INTO uuid_acks (uuid, uuid_hi, uuid_lo, parent_uuid, exchange_order_id,
                                  fill_count, remaining_count, avg_price_cents, ts)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (uuid) DO NOTHING""",
        (a["uuid"], a["uuid_hi"], a["uuid_lo"], a["parent_uuid"], a["exchange_order_id"],
         fill_count, remaining_count, avg_price_cents, a["ts"]))


def reconcile(cur, client_order_id: str) -> dict | None:
    """Resolve an exchange ack to its order by low-42 bitmask — NO lookup table.

    PG bitwise & on the signed BIGINT uses two's-complement semantics, so
    (uuid_lo & (2^42-1)) yields the unsigned low-42 tail; compare to the
    unsigned key directly.
    """
    key = int(client_order_id, 16) & MASK42
    cur.execute(
        """SELECT uuid, ticker, side, price_cents, count, status, mode
           FROM uuid_orders WHERE (uuid_lo & 4398046511103) = %s LIMIT 1""",
        (key,))
    row = cur.fetchone()
    if not row:
        return None
    return {"uuid": row[0], "ticker": row[1], "side": row[2],
            "price_cents": row[3], "count": row[4], "status": row[5], "mode": row[6]}


def settle(cur, ticker: str, market_uuid: str, settle_cents: int, *, ts: int | None = None):
    """Apply settlement: realized P&L = net_count * (settle - avg_entry) per side, then flatten."""
    ts = ts or int(time.time())
    m = mint_mark(ticker, market_uuid, settle_cents, kind="settle", ts=ts)
    cur.execute(
        """INSERT INTO uuid_marks (uuid, uuid_hi, uuid_lo, parent_uuid, ticker, mark_cents, kind, ts)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (uuid) DO NOTHING""",
        (m["uuid"], m["uuid_hi"], m["uuid_lo"], m["parent_uuid"], ticker, settle_cents, "settle", ts))
    cur.execute("SELECT side, net_count, avg_price_cents FROM uuid_positions WHERE ticker=%s", (ticker,))
    for side, net, avg in cur.fetchall():
        if net == 0:
            continue
        # YES settles at settle_cents; NO settles at 100 - settle_cents
        px = settle_cents if side == "yes" else (100 - settle_cents)
        realized = int(round(net * (px - avg)))
        cur.execute(
            """UPDATE uuid_positions SET realized_pnl_cents = realized_pnl_cents + %s,
               net_count = 0, updated_ts = %s WHERE ticker=%s AND side=%s""",
            (realized, ts, ticker, side))
    return m


def apply_fill_to_position(cur, ticker: str, side: str, market_uuid: str,
                           price_cents: int, count: int, ts: int):
    cur.execute("SELECT net_count, avg_price_cents FROM uuid_positions WHERE ticker=%s AND side=%s",
                (ticker, side))
    row = cur.fetchone()
    if row and row[0] != 0:
        net, avg = row
        new_net = net + count
        new_avg = ((net * avg) + (count * price_cents)) / new_net if new_net else 0.0
        cur.execute(
            """UPDATE uuid_positions SET net_count=%s, avg_price_cents=%s, updated_ts=%s
               WHERE ticker=%s AND side=%s""", (new_net, new_avg, ts, ticker, side))
    else:
        cur.execute(
            """INSERT INTO uuid_positions (ticker, side, market_uuid, net_count, avg_price_cents, updated_ts)
               VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT (ticker, side) DO UPDATE SET net_count=EXCLUDED.net_count,
                 avg_price_cents=EXCLUDED.avg_price_cents, updated_ts=EXCLUDED.updated_ts""",
            (ticker, side, market_uuid, count, float(price_cents), ts))


def pnl_rollup(cur, ticker: str | None = None) -> list[dict]:
    q = "SELECT market_uuid, ticker, orders, filled_contracts, notional_cents, fees_cents FROM uuid_pnl"
    args: tuple = ()
    if ticker:
        q += " WHERE ticker=%s"
        args = (ticker,)
    cur.execute(q, args)
    cols = ["market_uuid", "ticker", "orders", "filled_contracts", "notional_cents", "fees_cents"]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def realized_pnl(cur, ticker: str | None = None) -> int:
    q = "SELECT coalesce(sum(realized_pnl_cents),0) FROM uuid_positions"
    args: tuple = ()
    if ticker:
        q += " WHERE ticker=%s"
        args = (ticker,)
    cur.execute(q, args)
    return int(cur.fetchone()[0])
