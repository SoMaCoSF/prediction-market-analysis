# FIRST REAL TRADE: pick liquid market -> FIRE 1 YES at ask -> track ack/fill/ledger
# Prints order/ack/fill data only. Never prints key material.
import base64
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import httpx
import sb

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8420"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"

pk = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()

def sign(method, path, ts):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key((ROOT / ".kalshi_key.pem").read_bytes(), password=None)
    sig = key.sign(f"{ts}{method}{path}".encode(),
                   padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                   hashes.SHA256())
    return base64.b64encode(sig).decode()

def kget(path):
    import os

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    kid = os.getenv("KALSHI_KEY_ID")
    ts = str(int(time.time() * 1000))
    h = {"KALSHI-ACCESS-KEY": kid, "KALSHI-ACCESS-SIGNATURE": sign("GET", path.split("?")[0], ts),
         "KALSHI-ACCESS-TIMESTAMP": ts}
    r = httpx.get(KALSHI + path, headers=h, timeout=20)
    return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text[:300]}

# 1) pinned target: KXMLB-26-LAD (deep, tight, unambiguous fill). Fresh quote first.
TARGET = "KXMLB-26-LAD"
r = httpx.get(f"https://api.elections.kalshi.com/trade-api/v2/markets/{TARGET}",
              headers={"Accept-Encoding": "identity"}, timeout=20)
mk = r.json()["market"]
ya_f = float(mk.get("yes_ask_dollars") or 0)
yb_f = float(mk.get("yes_bid_dollars") or 0)
m = {"ticker": TARGET, "title": mk.get("title"),
     "yes_bid": round(yb_f * 100), "yes_ask": round(ya_f * 100),
     "ask_size": float(mk.get("yes_ask_size_fp") or 0), "volume": float(mk.get("volume_fp") or 0)}
print(f"TARGET: {m['ticker']}")
print(f"  title: {m['title']}")
print(f"  yes_bid={m['yes_bid']} yes_ask={m['yes_ask']} ask_size={m['ask_size']} vol={m['volume']}")
assert 1 <= m["yes_ask"] <= 99 and m["ask_size"] >= 1, "no resting ask — aborting"

# 2) FIRE 1 YES at the ask (taker)
price = int(m["yes_ask"])
body = {"ticker": m["ticker"], "side": "yes", "price": price, "count": 1,
        "mode": "live", "passkey": pk, "confirm": "FIRE"}
r = httpx.post(f"{BASE}/api/order", json=body, timeout=30)
print(f"\nFIRE -> HTTP {r.status_code}")
resp = r.json()
print(json.dumps(resp, indent=2)[:1200])
if r.status_code != 200 or not resp.get("ok"):
    print("FIRE FAILED — see above")
    sys.exit(1)

oid = resp.get("exchange_order_id")
coi = resp.get("client_order_id")
uuid = resp.get("uuid")
print(f"\nACK: exchange_order_id={oid}  client_order_id={coi}  uuid={uuid}")

# 3) poll exchange order status
time.sleep(2)
code, o = kget(f"/portfolio/orders/{oid}")
print(f"\nexchange order status: HTTP {code}")
print(json.dumps(o, indent=2)[:900])

# 4) exchange fills for this order
code, f = kget(f"/portfolio/fills?order_id={oid}")
print(f"\nexchange fills: HTTP {code}")
print(json.dumps(f, indent=2)[:900])

# 5) ledger reconciliation view
led = httpx.get(f"{BASE}/api/orders", timeout=15).json()["orders"]
hit = [x for x in led if x["client_order_id"] == coi]
print("\nledger row:", json.dumps(hit[0], indent=2) if hit else "NOT FOUND")
print("\nFIRST-TRADE TRACK COMPLETE")
