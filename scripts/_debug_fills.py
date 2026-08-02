# debug: raw fills from exchange (unfiltered + by ticker), find the NO fill
import base64
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"

def sign(method, path, ts):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key((ROOT / ".kalshi_key.pem").read_bytes(), password=None)
    sig = key.sign(f"{ts}{method}{path}".encode(),
                   padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                   hashes.SHA256())
    return base64.b64encode(sig).decode()

def kget(path):
    ts = str(int(time.time() * 1000))
    full = "/trade-api/v2" + path.split("?")[0]
    h = {"KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"),
         "KALSHI-ACCESS-SIGNATURE": sign("GET", full, ts),
         "KALSHI-ACCESS-TIMESTAMP": ts}
    r = httpx.get(KALSHI + path, headers=h, timeout=20)
    return r.status_code, r.json() if "json" in r.headers.get("content-type", "") else {"raw": r.text[:300]}

code, d = kget("/portfolio/fills?limit=20")
print("unfiltered:", code, "count:", len(d.get("fills") or []), "cursor:", repr(d.get("cursor")))
for f in (d.get("fills") or [])[:10]:
    print(f"  {f.get('ticker') or f.get('market_ticker')} {f.get('side')} {f.get('count_fp')} @ {f.get('yes_price_dollars')}/{f.get('no_price_dollars')} oid={str(f.get('order_id'))[:13]} ts={f.get('ts')}")
print("\nby ticker KXBTC15M:")
code, d2 = kget("/portfolio/fills?ticker=KXBTC15M-26AUG021515-15&limit=10")
print("  ", code, json.dumps(d2)[:400])
print("\nby min_ts:")
code, d3 = kget("/portfolio/fills?min_ts=1785696000&limit=20")
print("  ", code, "count:", len(d3.get("fills") or []))
