# file_id: SOM-PY-0917-v1.0.0 name: proof_ledger.py description: Transaction-level proof for the UUID trading ledger — order->fills->reconcile->settle->P&L, inside a rolled-back transaction (no DB pollution) project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [proof, ledger, uuid, pnl, reconciliation] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""proof_ledger.py — prove the UUID trading ledger end-to-end.

Lifecycle proven (all inside ONE transaction that is ROLLED BACK at the end):
  1. mint market root (0x3B0) + order 3 YES @ 42c (0x3A4, child of market)
  2. client_order_id == hex(order low-42 tail)            [reconciliation key]
  3. record order + two fills (2 @ 42c, 1 @ 42c)          [0x3A7 children]
  4. bitmask routing: (uuid_hi >> 52) & 0xFFF matches each type code
  5. reconcile: exchange-style ack (client_order_id only) -> finds the order
  6. position avg entry = 42c; settle YES @ 100c
  7. realized P&L = 3 * (100 - 42) = 174c
  8. spawn-tree walk: market -> orders -> fills counts

Usage:
  .venv311/Scripts/python scripts/proof_ledger.py
Exit 0 = ALL VERIFIED, 1 = failure. Leaves ZERO rows behind (ROLLBACK).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uuid_ledger as L  # noqa: E402

TICKER = "PROOF-LEDGER-TEST"
fails: list[str] = []


def check(name: str, ok: bool, detail: str = ""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not ok:
        fails.append(name)


def main() -> int:
    con = L.local_conn()
    con.autocommit = False
    cur = con.cursor()

    # ensure schema exists (idempotent, commits separately outside txn is fine for DDL IF NOT EXISTS)
    schema = (Path(__file__).resolve().parent / "ledger_schema.sql").read_text()
    cur.execute(schema)

    ts = 1_800_000_000

    # 1) market + order
    mkt = L.mint_market_uuid(TICKER, ts=ts)
    check("market type 0x3B0", (int(mkt.replace('-', '')[:16], 16) >> 52) & 0xFFF == 0x3B0)
    order = L.mint_order(TICKER, "yes", 42, 3, parent_uuid=mkt, ts=ts)
    check("order type 0x3A4 via bitmask",
          (order["uuid_hi"] >> 52) & 0xFFF == 0x3A4, order["uuid"])
    d = L.decode_gyst(order["uuid"])
    check("order is child: depth=1 gen=1", d.fractal_depth == 1 and d.fractal_generation == 1)
    check("order signal = 0.42", abs(d.signal_normalized - 0.42) < 1e-3, f"{d.signal_normalized:.4f}")

    # 2) client_order_id == low-42 tail
    check("client_order_id == hex(low-42)",
          int(order["client_order_id"], 16) == L.lo42(order["uuid"]),
          order["client_order_id"])

    # 3) record order + 2 fills
    L.record_order(cur, order, mode="paper", status="filled")
    f1 = L.mint_fill(order["uuid"], 42, 2, ts=ts, fill_seq=1)
    f2 = L.mint_fill(order["uuid"], 42, 1, ts=ts, fill_seq=2)
    L.record_fill(cur, f1, fee_cents=0)
    L.record_fill(cur, f2, fee_cents=0)
    L.apply_fill_to_position(cur, TICKER, "yes", mkt, 42, 3, ts)
    check("fill type 0x3A7 via bitmask", (f1["uuid_hi"] >> 52) & 0xFFF == 0x3A7)
    check("fill parent == order uuid", f1["parent_uuid"] == order["uuid"])

    # 5) reconcile by ack (client_order_id only)
    hit = L.reconcile(cur, order["client_order_id"])
    check("reconcile ack -> order", hit is not None and hit["uuid"] == order["uuid"],
          str(hit))
    miss = L.reconcile(cur, "deadbeef01")
    check("reconcile unknown ack -> None", miss is None)

    # 6) position
    cur.execute("SELECT net_count, avg_price_cents FROM uuid_positions WHERE ticker=%s AND side='yes'", (TICKER,))
    net, avg = cur.fetchone()
    check("position 3 @ 42c avg", net == 3 and abs(avg - 42.0) < 1e-9, f"{net} @ {avg}")

    # 7) settle YES @ 100 -> realized = 3*(100-42) = 174
    mark = L.settle(cur, TICKER, mkt, 100, ts=ts + 60)
    check("settle mark type 0x3A9", (mark["uuid_hi"] >> 52) & 0xFFF == 0x3A9)
    realized = L.realized_pnl(cur, TICKER)
    check("realized P&L == 174c", realized == 174, f"{realized}c")
    cur.execute("SELECT net_count FROM uuid_positions WHERE ticker=%s AND side='yes'", (TICKER,))
    check("position flattened after settle", cur.fetchone()[0] == 0)

    # 8) spawn-tree rollup
    roll = L.pnl_rollup(cur, TICKER)
    ok = (len(roll) == 1 and roll[0]["orders"] == 1 and roll[0]["filled_contracts"] == 3
          and roll[0]["notional_cents"] == 126)
    check("rollup: 1 order, 3 contracts, 126c notional", ok, str(roll))

    # determinism: re-mint same logical order -> identical UUID (idempotent retry)
    order2 = L.mint_order(TICKER, "yes", 42, 3, parent_uuid=mkt, ts=ts)
    check("idempotent re-mint same UUID", order2["uuid"] == order["uuid"])

    con.rollback()
    con.close()

    print()
    if fails:
        print(f"RESULT: {len(fails)} FAILURE(S): {fails}  (rolled back, no rows written)")
        return 1
    print("RESULT: LEDGER VERIFIED — order/fill/reconcile/settle/P&L all consistent  (rolled back, no rows written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
