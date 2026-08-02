# backfill the bot's NO trade: fetch exchange fill -> record 0x3A7 fill + position -> settle -> realized
import base64
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import httpx
import sb
import uuid_ledger as L
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
TICKER = "KXBTC15M-26AUG021515-15"

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
    return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text[:300]}

con = sb.sb_conn()
cur = con.cursor()
cur.execute("SELECT uuid, exchange_order_id, side, price_cents FROM uuid_orders WHERE ticker=%s AND mode='live'", (TICKER,))
order_uuid, xid, side, px = cur.fetchone()
print("order:", order_uuid[:20], "xid:", xid, "side:", side)

code, f = kget(f"/portfolio/fills?ticker={TICKER}&limit=10")
fills = f.get("fills") or []
print("exchange fills:", code, len(fills))
mkt = L.mint_market_uuid(TICKER)
for fl in fills:
    if str(fl.get("order_id")) != str(xid):
        continue
    fid = str(fl.get("fill_id") or fl.get("trade_id"))
    pxf = float(fl.get("no_price_dollars") or fl.get("yes_price_dollars") or 0)
    pxc = int(round(pxf * 100))
    cnt = int(round(float(fl.get("count_fp") or 1)))
    fee = int(round(float(fl.get("fee_cost") or 0) * 100))
    fu = L.mint_fill(order_uuid, pxc, cnt, exchange_fill_id=fid)
    L.record_fill(cur, fu, fee_cents=fee, exchange_fill_id=fid)
    L.apply_fill_to_position(cur, TICKER, side, mkt, pxc, cnt, fu["ts"])
    print(f"fill {fid[:13]} px={pxc}c cnt={cnt} fee={fee}c -> 0x3A7 {fu['uuid'][:20]}")
con.commit()

# settle at result=no -> NO side settles at 100
m = L.settle(cur, TICKER, mkt, 0)   # settle_cents=0 means YES=0; NO settles at 100-0=100
con.commit()
cur.execute("SELECT side, net_count, realized_pnl_cents FROM uuid_positions WHERE ticker=%s", (TICKER,))
print("positions after settle:", cur.fetchall())
con.close()
print("BACKFILL COMPLETE")
