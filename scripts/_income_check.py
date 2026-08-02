# income-now: price check on open crypto positions -> sell winners at bid (taker), realize cash
import base64
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

def kreq(method, path, body=None):
    ts = str(int(time.time() * 1000))
    full = "/trade-api/v2" + path.split("?")[0]
    h = {"KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"),
         "KALSHI-ACCESS-SIGNATURE": sign(method, full, ts),
         "KALSHI-ACCESS-TIMESTAMP": ts,
         "Content-Type": "application/json"}
    r = httpx.request(method, KALSHI + path, json=body, headers=h, timeout=20)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:200]}

# our crypto 15M entries from the play
entries = {
    "KXXRP15M-26AUG021545-45": 25,
    "KXDOGE15M-26AUG021545-45": 42,
    "KXSOL15M-26AUG021545-45": 44,
    "KXETH15M-26AUG021545-45": 47,
}

with httpx.Client(headers={"Accept-Encoding": "identity"}) as cx:
    for t, entry in entries.items():
        r = cx.get(f"{KALSHI}/markets/{t}", timeout=15)
        m = r.json().get("market", {})
        yb = float(m.get("yes_bid_dollars") or 0) * 100
        ya = float(m.get("yes_ask_dollars") or 0) * 100
        res = m.get("result") or ""
        print(f"{t}: entry={entry}c bid={yb:.1f}c ask={ya:.1f}c result={res!r} status={m.get('status')}")

print("\n--- balance before ---")
code, bal = kreq("GET", "/portfolio/balance")
print("cash:", bal.get("balance_dollars"), "portfolio:", bal.get("portfolio_value"))
