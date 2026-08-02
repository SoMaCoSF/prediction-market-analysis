# full reconcile: exchange positions + open orders vs our ledger, after the parallel play
import base64
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import httpx
import sb
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

code, bal = kget("/portfolio/balance")
print("CASH:", bal.get("balance_dollars"), "| portfolio_value:", bal.get("portfolio_value"))

code, pos = kget("/portfolio/positions?limit=100")
print("\n=== EXCHANGE POSITIONS (truth) ===")
total_cost = 0.0
for mp in pos.get("market_positions", []):
    fp = float(mp.get("position_fp") or 0)
    if fp == 0:
        continue
    cost = float(mp.get("total_traded_dollars") or 0)
    fees = float(mp.get("fees_paid_dollars") or 0)
    total_cost += cost
    print(f"  {mp['ticker']:38s} {fp:5.1f}ct cost=${cost:.3f} fees=${fees:.4f}")
print(f"  TOTAL cost basis: ${total_cost:.2f}")

code, oo = kget("/portfolio/orders?status=resting&limit=50")
print("\n=== RESTING ORDERS (unfilled, live) ===")
for o in (oo.get("orders") or []):
    print(f"  {o['ticker']:38s} {o.get('side')}/{o.get('action')} {o.get('yes_price_dollars') or o.get('no_price_dollars')} rem={o.get('remaining_count_fp')}")

# ledger side
con = sb.sb_conn()
cur = con.cursor()
cur.execute("SELECT ticker, side, price_cents, count, status FROM uuid_orders WHERE mode='live' ORDER BY created_at DESC LIMIT 15")
print("\n=== LEDGER live orders (last 15) ===")
for r in cur.fetchall():
    print(f"  {r[0]:38s} {r[1]:3s} {r[2]}c x{r[3]} {r[4]}")
con.close()
