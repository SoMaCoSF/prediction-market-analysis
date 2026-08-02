# fetch the real fill via V2, mint+record the 0x3A7 fill child + position, show spawn tree
import base64
import json
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
OID = "a410c673-6cad-4747-96d0-f8ac5fca5145"

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
    full = "/trade-api/v2" + path.split("?")[0]   # signature covers the FULL path
    h = {"KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"),
         "KALSHI-ACCESS-SIGNATURE": sign("GET", full, ts),
         "KALSHI-ACCESS-TIMESTAMP": ts}
    r = httpx.get(KALSHI + path, headers=h, timeout=20)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:300]}

code, o = kget(f"/portfolio/orders/{OID}")
print("V2 order status:", code)
print(json.dumps(o, indent=2)[:800])

code, f = kget("/portfolio/fills?ticker=KXMLB-26-LAD&limit=5")
print("\nfills:", code)
print(json.dumps(f, indent=2)[:900])

# record the fill into the ledger (idempotent via exchange-seeded UUID)
fills = (f.get("fills") or []) if code == 200 else []
con, cur = sb.sb_conn(), None
cur = con.cursor()
cur.execute("SELECT uuid, parent_uuid, price_cents, count FROM uuid_orders WHERE exchange_order_id=%s", (OID,))
row = cur.fetchone()
print("\nledger order:", row)
if row and fills:
    order_uuid, mkt, _, _ = row
    n = 0
    for fl in fills:
        fid = fl.get("fill_id") or fl.get("trade_id") or f"{OID}:{n}"
        px_f = fl.get("yes_price_dollars") or fl.get("price_dollars") or fl.get("price") or 0
        px = int(round(float(px_f) * 100)) if float(px_f) <= 1.0 else int(round(float(px_f)))
        cnt_f = fl.get("count_fp") or fl.get("count") or 1
        cnt = int(round(float(cnt_f)))
        fee_f = fl.get("fee_paid_dollars") or 0
        fee = int(round(float(fee_f) * 100))
        fu = L.mint_fill(order_uuid, px, cnt, exchange_fill_id=str(fid))
        L.record_fill(cur, fu, fee_cents=fee, exchange_fill_id=str(fid))
        L.apply_fill_to_position(cur, "KXMLB-26-LAD", "yes", mkt, px, cnt, fu["ts"])
        n += 1
    con.commit()
    print(f"recorded {n} fill(s) as 0x3A7 children + position updated")

# spawn tree walk
cur.execute("SELECT uuid, 'order' k FROM uuid_orders WHERE exchange_order_id=%s", (OID,))
tree = cur.fetchall()
cur.execute("SELECT uuid, 'ack' FROM uuid_acks WHERE exchange_order_id=%s", (OID,))
tree += cur.fetchall()
cur.execute("SELECT f.uuid, 'fill' FROM uuid_fills f JOIN uuid_orders o ON f.parent_uuid=o.uuid WHERE o.exchange_order_id=%s", (OID,))
tree += cur.fetchall()
print("\n=== SPAWN TREE (all bitmask-decodable) ===")
for u, k in tree:
    d = L.decode_gyst(u)
    print(f"  {k:6s} {u}  type=0x{d.type_code:X} depth={d.fractal_depth} sig={d.signal_normalized:.4f}")
cur.execute("SELECT net_count, avg_price_cents FROM uuid_positions WHERE ticker='KXMLB-26-LAD' AND side='yes'")
print("position:", cur.fetchone())
con.close()
