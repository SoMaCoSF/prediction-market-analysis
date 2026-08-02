# settle check: 15M positions from the play + balance + resting order fates
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

def kget(path):
    ts = str(int(time.time() * 1000))
    h = {"KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"),
         "KALSHI-ACCESS-SIGNATURE": sign("GET", "/trade-api/v2" + path.split("?")[0], ts),
         "KALSHI-ACCESS-TIMESTAMP": ts}
    r = httpx.get(KALSHI + path, headers=h, timeout=20)
    return r.status_code, r.json() if "json" in r.headers.get("content-type", "") else {"raw": r.text[:200]}

with httpx.Client(headers={"Accept-Encoding": "identity"}) as cx:
    for t in ["KXXRP15M-26AUG021545-45", "KXDOGE15M-26AUG021545-45", "KXSOL15M-26AUG021545-45", "KXETH15M-26AUG021545-45"]:
        r = cx.get(f"{KALSHI}/markets/{t}", timeout=15)
        m = r.json().get("market", {})
        print(f"{t}: result={m.get('result')!r} status={m.get('status')}")

code, bal = kget("/portfolio/balance")
print("\nCASH:", bal.get("balance_dollars"), "| portfolio_value:", bal.get("portfolio_value"))
code, pos = kget("/portfolio/positions?limit=100")
n = 0
for mp in pos.get("market_positions", []):
    if float(mp.get("position_fp") or 0) != 0:
        n += 1
        print(f"  open: {mp['ticker']:36s} {mp['position_fp']}ct cost=${mp.get('total_traded_dollars')}")
print(f"({n} open positions)")
