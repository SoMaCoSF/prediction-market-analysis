# truth check: exchange status of the bot's NO order
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
OID = "b0be585a-af90-43d5-9817-1dc46b67adbf"

def sign(method, path, ts):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key((ROOT / ".kalshi_key.pem").read_bytes(), password=None)
    sig = key.sign(f"{ts}{method}{path}".encode(),
                   padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                   hashes.SHA256())
    return base64.b64encode(sig).decode()

ts = str(int(time.time() * 1000))
h = {"KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"),
     "KALSHI-ACCESS-SIGNATURE": sign("GET", f"/trade-api/v2/portfolio/orders/{OID}", ts),
     "KALSHI-ACCESS-TIMESTAMP": ts}
r = httpx.get(f"{KALSHI}/portfolio/orders/{OID}", headers=h, timeout=20)
print("HTTP", r.status_code)
print(json.dumps(r.json(), indent=2)[:1200])

# also: current balance + positions on exchange
ts = str(int(time.time() * 1000))
h["KALSHI-ACCESS-SIGNATURE"] = sign("GET", "/trade-api/v2/portfolio/balance", ts)
h["KALSHI-ACCESS-TIMESTAMP"] = ts
r = httpx.get(f"{KALSHI}/portfolio/balance", headers=h, timeout=20)
print("\nbalance:", r.status_code, json.dumps(r.json())[:300])

ts = str(int(time.time() * 1000))
h["KALSHI-ACCESS-SIGNATURE"] = sign("GET", "/trade-api/v2/portfolio/positions", ts)
h["KALSHI-ACCESS-TIMESTAMP"] = ts
r = httpx.get(f"{KALSHI}/portfolio/positions", headers=h, timeout=20)
print("\npositions:", r.status_code, json.dumps(r.json())[:600])
