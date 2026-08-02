# discover Kalshi 15-min BTC series + currently open markets with books
import httpx

CANDIDATES = ["KXBTC15M", "KXBTC15MIN", "KXBTC15", "KXBTCD", "KXBTC1H", "KXBTCHOUR", "KXBTC"]
with httpx.Client(timeout=30, headers={"Accept-Encoding": "identity"}) as cx:
    for s in CANDIDATES:
        try:
            r = cx.get("https://api.elections.kalshi.com/trade-api/v2/markets",
                       params={"limit": 20, "status": "open", "series_ticker": s})
            ms = r.json().get("markets", [])
        except Exception as e:
            print(f"{s}: ERR {repr(e)[:60]}")
            continue
        if not ms:
            print(f"{s}: 0 open")
            continue
        print(f"{s}: {len(ms)} open")
        for m in ms[:3]:
            ya = m.get("yes_ask_dollars")
            print(f"   {m['ticker'][:60]:60s} ask={ya} close={m.get('close_time','')[:19]} vol={m.get('volume_fp')}  {(m.get('title') or '')[:50]}")
