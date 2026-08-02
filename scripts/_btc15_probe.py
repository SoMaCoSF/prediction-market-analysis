# pre-launch probe: MC up+keys, spot feed, momentum, KXBTC15M discovery (no fires)
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import btc15_bot as B
import httpx

s = httpx.get(f"{B.MC}/api/stats", timeout=10).json()
print("MC:", "UP", "| keys:", s["keys"], "| kill:", s["kill"], "| corpus:", s["corpus"]["online"])
assert s["keys"] and not s["kill"]

with httpx.Client(headers={"Accept-Encoding": "identity"}) as cx:
    px = B.spot_price(cx)
    print("BTC spot:", px)
    assert px and px > 1000
    for _ in range(3):
        B.spot_hist.append((time.time(), px))
        time.sleep(1)
    m = B.current_market(cx)
    print("market:", m)
    assert m and m["ticker"].startswith("KXBTC15M")
    print(f"ttl: {m['ttl']:.0f}s | yes {m['yes_bid']}/{m['yes_ask']} | no_ask={100-m['yes_bid']}")
print("PROBE OK — bot components live")
