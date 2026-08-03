# file_id: SOM-PY-0958-v1.0.0 name: finance_tally.py description: Financial tally — Kalshi equity decomposition (cash, positions by sleeve), day flows, allocation report project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [finance, tally, allocation, kalshi] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""finance_tally.py — where is every dollar, right now. Zero tokens."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from run_report import kget  # noqa: E402

DAY_START = 24.98


def main():
    bal = kget("/portfolio/balance")
    cash = float(bal.get("balance_dollars") or 0)
    pv = (bal.get("portfolio_value") or 0) / 100
    sleeves = defaultdict(lambda: {"n": 0, "cost": 0.0})
    pos = kget("/portfolio/positions?limit=200")
    for mp in pos.get("market_positions", []):
        fp = float(mp.get("position_fp") or 0)
        if fp == 0:
            continue
        t = mp.get("ticker", "")
        cost = abs(float(mp.get("total_traded_dollars") or 0))
        sleeve = ("crypto-15M" if "15M" in t else
                  "mve-tails" if "KXMV" in t else
                  "sports-futures" if t.startswith(("KXMLB", "KXNBA", "KXNFL")) else "other")
        sleeves[sleeve]["n"] += 1
        sleeves[sleeve]["cost"] += cost
    print("=" * 56)
    print("FINANCIAL TALLY — real allocation, right now")
    print("=" * 56)
    print("\nKALSHI (exchange truth)")
    print(f"  cash:              ${cash:>8.2f}")
    print(f"  positions (mark):  ${pv:>8.2f}")
    print(f"  EQUITY:            ${cash + pv:>8.2f}")
    print(f"  day start:         ${DAY_START:>8.2f}")
    print(f"  day P&L:           ${cash + pv - DAY_START:>+8.2f} ({(cash + pv - DAY_START) / DAY_START * 100:+.0f}%)")
    print("\nALLOCATION BY SLEEVE (cost basis)")
    for s, d in sorted(sleeves.items(), key=lambda x: -x[1]["cost"]):
        print(f"  {s:16s} {d['n']:>4d} pos   ${d['cost']:>7.2f}")
    print("\nCOST SIDE (monthly, user-reported)")
    print("  Kimi/Nous credits: ~$40 budget (today: heavy build day)")
    print("  Vercel:            $0 (hobby)")
    print("  Supabase:          $0 (free tier)")
    print("  GPU/power:         ~$0 (GTX 1660 Ti idle-ish)")
    print("\nEXTERNAL (no API — user to fill)")
    print("  Venmo balance:     $____ (debit card rail ready)")
    print("  Bank:              $____")
    print("=" * 56)


if __name__ == "__main__":
    sys.exit(main())
