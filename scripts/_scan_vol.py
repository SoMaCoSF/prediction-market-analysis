# scan all high-frequency (15M/1H) Kalshi series + spot vol comparison + BTC15 settle check
import httpx

SERIES = ["KXBTC15M", "KXETH15M", "KXSOL15M", "KXXRP15M", "KXDOGE15M", "KXADA15M",
          "KXBTC1H", "KXETH1H", "KXSOL1H", "KXBTCD", "KXETHD", "KXSOLD"]
found = []
with httpx.Client(timeout=20, headers={"Accept-Encoding": "identity"}) as cx:
    for s in SERIES:
        try:
            r = cx.get("https://api.elections.kalshi.com/trade-api/v2/markets",
                       params={"limit": 10, "status": "open", "series_ticker": s})
            ms = r.json().get("markets", [])
        except Exception as e:
            print(f"{s:10s} ERR {repr(e)[:50]}")
            continue
        if not ms:
            print(f"{s:10s} 0 open")
            continue
        m = ms[0]
        vol = float(m.get("volume_fp") or 0)
        ya = m.get("yes_ask_dollars")
        print(f"{s:10s} {len(ms)} open | eg {m['ticker'][:42]:42s} ask={ya} vol={vol:.0f}")
        found.append(s)

    print("\n=== settle check: our short ===")
    r = cx.get("https://api.elections.kalshi.com/trade-api/v2/markets/KXBTC15M-26AUG021515-15", timeout=15)
    m = r.json()["market"]
    print("result:", repr(m.get("result")), "| status:", m.get("status"), "| last YES:", m.get("last_price_dollars"))

    print("\n=== spot 24h moves (coinbase) ===")
    for sym in ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]:
        try:
            d = cx.get(f"https://api.coinbase.com/v2/prices/{sym}/spot", timeout=8).json()["data"]
            print(f"  {sym:8s} {float(d['amount']):,.2f}")
        except Exception as e:
            print(f"  {sym:8s} err {repr(e)[:40]}")
