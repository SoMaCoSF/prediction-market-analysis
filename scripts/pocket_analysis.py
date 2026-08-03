# file_id: SOM-PY-0985-v1.0.0 name: pocket_analysis.py description: Where does the engine actually win — settle outcomes by series/side/entry-band from the ledger; the concentration map; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [analysis, expectancy, concentration, evidence] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""pocket_analysis.py — find the winning pocket. Read-only."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import sb  # noqa: E402


def series_of(t):
    for s in ("BTC", "ETH", "SOL", "XRP", "DOGE"):
        if f"KX{s}15M" in t:
            return s
    return "OTHER"


def band_of(p):
    p = p or 0
    return "<30c" if p < 30 else "30-50c" if p < 50 else "50-65c" if p < 65 else "65c+"


def main():
    con = sb.sb_conn()
    cur = con.cursor()
    cur.execute("SELECT ticker, side, avg_price_cents, realized_pnl_cents FROM uuid_positions WHERE realized_pnl_cents != 0")
    rows = cur.fetchall()
    con.close()
    agg = defaultdict(lambda: [0, 0, 0])
    for t, side, px, pnl in rows:
        for key in [("SERIES", series_of(t)), ("SIDE", side or "?"), ("BAND", band_of(px)),
                    ("COMBO", f"{series_of(t)}-{side}")]:
            a = agg[key]
            a[0] += 1
            a[1] += 1 if (pnl or 0) > 0 else 0
            a[2] += pnl or 0
    print(f"settle outcomes analyzed: {len(rows)}")
    for (kind, name), (n, w, pnl) in sorted(agg.items()):
        if n >= 3:
            print(f"{kind:7s} {name:10s} n={n:3d} wr={w/n*100:4.0f}% pnl=${pnl/100:+7.2f} exp={pnl/n:+5.1f}c/trade")


if __name__ == "__main__":
    main()
