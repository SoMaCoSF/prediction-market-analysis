# scan Kalshi open markets for real two-sided liquid books (2c..98c ask, size, volume)
import httpx

cur = None
live = []
with httpx.Client(timeout=30, headers={"Accept-Encoding": "identity"}) as cx:
    for _ in range(4):
        params = {"limit": 1000, "status": "open"}
        if cur:
            params["cursor"] = cur
        r = cx.get("https://api.elections.kalshi.com/trade-api/v2/markets", params=params)
        d = r.json()
        for m in d["markets"]:
            try:
                ya = float(m.get("yes_ask_dollars") or 0)
                yb = float(m.get("yes_bid_dollars") or 0)
                vol = float(m.get("volume_fp") or 0)
                sz = float(m.get("yes_ask_size_fp") or 0)
            except Exception:
                continue
            if 0.02 <= ya <= 0.98 and vol > 0 and sz >= 1:
                live.append((vol, m["ticker"], yb, ya, sz, (m.get("title") or "")[:60]))
        cur = d.get("cursor")
        if not cur:
            break

print("two-sided liquid markets:", len(live))
live.sort(key=lambda x: -x[0])
for vol, t, yb, ya, sz, title in live[:12]:
    print(f"{t[:52]:52s} bid {yb:5.2f} ask {ya:5.2f} size {sz:7.0f} vol {vol:10.0f}  {title}")
