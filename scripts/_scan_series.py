# scan known-liquid Kalshi series for the best first-trade candidate
import httpx

SERIES = ["KXBTC", "KXETH", "KXSOL", "KXFED", "KXCPI", "KXMLB", "KXNBA", "KXNFL",
          "KXNASDAQ100", "KXSP500", "KXRATE", "KXPRES", "KXHIGHNY", "KXEURUSD"]
rows = []
with httpx.Client(timeout=30, headers={"Accept-Encoding": "identity"}) as cx:
    for s in SERIES:
        try:
            r = cx.get("https://api.elections.kalshi.com/trade-api/v2/markets",
                       params={"limit": 200, "status": "open", "series_ticker": s})
            ms = r.json().get("markets", [])
        except Exception as e:
            print(f"{s}: fetch err {repr(e)[:80]}")
            continue
        for m in ms:
            try:
                ya = float(m.get("yes_ask_dollars") or 0)
                yb = float(m.get("yes_bid_dollars") or 0)
                vol = float(m.get("volume_fp") or 0)
                sz = float(m.get("yes_ask_size_fp") or 0)
                bsz = float(m.get("yes_bid_size_fp") or 0)
            except Exception:
                continue
            if 0.02 <= ya <= 0.98 and vol > 0 and sz >= 1:
                spread = ya - yb
                rows.append((vol, spread, m["ticker"], yb, ya, sz, bsz, (m.get("title") or "")[:55]))
        if ms:
            print(f"{s}: {len(ms)} open markets")

print("\n=== best candidates (vol desc) ===")
rows.sort(key=lambda x: -x[0])
for vol, spread, t, yb, ya, sz, _bsz, title in rows[:12]:
    print(f"{t[:48]:48s} bid {yb:5.2f} ask {ya:5.2f} sprd {spread:4.2f} asz {sz:6.0f} vol {vol:9.0f}  {title}")
