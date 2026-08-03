# file_id: SOM-PY-0963-v1.0.0 name: lanes_report.py description: Lanes of returns — per-engine P&L decomposition (momentum / parlay / sports / news lanes) from the ledger + exchange truth; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [lanes, returns, pnl, report] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""lanes_report.py — every lane of returns, quantified."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import sb  # noqa: E402
from run_report import kget  # noqa: E402

LANES = [
    ("momentum-15M", "btctrend+scalp live momentum", lambda t: "15M" in t),
    ("parlay-tails", "parlay loop combo tails", lambda t: "KXMV" in t),
    ("sports-futures", "long-dated sports", lambda t: t.startswith(("KXMLB", "KXNBA", "KXNFL", "KXATP", "KXWTA", "KXITF"))),
    ("news-forecast", "news/supply-chain forecasts", lambda t: t.startswith(("KXWTI", "KXNASDAQ", "KXSP500", "KXWHEAT"))),
]


def lane_of(ticker):
    for name, _, pred in LANES:
        if pred(ticker):
            return name
    return "other"


def main():
    bal = kget("/portfolio/balance")
    cash = float(bal.get("balance_dollars") or 0)
    pv = (bal.get("portfolio_value") or 0) / 100
    con = sb.sb_conn()
    cur = con.cursor()
    cur.execute("SELECT ticker, net_count, avg_price_cents, realized_pnl_cents FROM uuid_positions")
    agg = defaultdict(lambda: {"open": 0, "cost": 0.0, "realized": 0})
    for t, net, avg, real in cur.fetchall():
        l = lane_of(t)
        agg[l]["open"] += net or 0
        agg[l]["cost"] += (net or 0) * (avg or 0) / 100.0
        agg[l]["realized"] += (real or 0) / 100.0
    con.close()
    print("=" * 64)
    print(f"LANES OF RETURNS — equity ${cash + pv:.2f} (cash ${cash:.2f} + marks ${pv:.2f})")
    print("=" * 64)
    total_real = 0.0
    for name, desc in LANES:
        d = agg.get(name, {"open": 0, "cost": 0.0, "realized": 0})
        total_real += d["realized"]
        print(f"\n[{name}] — {desc}")
        print(f"  open contracts: {d['open']:>5}   cost in play: ${d['cost']:>7.2f}   realized: ${d['realized']:+.2f}")
    o = agg.get("other", {"open": 0, "cost": 0.0, "realized": 0})
    total_real += o["realized"]
    print(f"\n[other]   open {o['open']} cost ${o['cost']:.2f} realized ${o['realized']:+.2f}")
    print(f"\nTOTAL realized across lanes: ${total_real:+.2f}")
    print("=" * 64)


if __name__ == "__main__":
    sys.exit(main())
