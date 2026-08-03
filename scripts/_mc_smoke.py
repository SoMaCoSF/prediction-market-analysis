# MC smoke test: stats, markets, paper order (passkey computed locally, never printed), tables
import hashlib
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sb

BASE = "http://127.0.0.1:8420"
time.sleep(1)

pk = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()

def show(name, r, n=400):
    body = r.text[:n]
    print(f"--- {name}: HTTP {r.status_code} ---")
    print(body)
    return r

r = show("GET /", httpx.get(f"{BASE}/", timeout=10), 200)
assert "<title>SOMACO // TRADE CONTROL</title>" in r.text, "index missing"

s = show("GET /api/stats", httpx.get(f"{BASE}/api/stats", timeout=30)).json()
assert "corpus" in s and "ledger" in s
print("corpus:", s["corpus"])
print("ledger:", s["ledger"], "kill:", s["kill"], "keys:", s["keys"])

m = show("GET /api/markets", httpx.get(f"{BASE}/api/markets", timeout=30), 300).json()
mkts = m.get("markets", [])
print(f"markets: {len(mkts)}; top: {mkts[0]['ticker'] if mkts else 'NONE'} vol={mkts[0]['volume'] if mkts else '-'}")

# paper order through the full pipeline (Supabase ledger)
tick = mkts[0]["ticker"] if mkts else "MC-SMOKE"
px = mkts[0].get("yes_ask") or 42 if mkts else 42
r = httpx.post(f"{BASE}/api/order", json={
    "ticker": tick, "side": "yes", "price": int(px), "count": 1,
    "mode": "paper", "passkey": pk}, timeout=30)
show("POST /api/order (paper)", r)
assert r.status_code == 200 and r.json().get("ok"), "paper order failed"
coi = r.json()["client_order_id"]

o = httpx.get(f"{BASE}/api/orders", timeout=15).json()["orders"]
hit = [x for x in o if x["client_order_id"] == coi]
print("order visible in ledger view:", bool(hit), "| status:", hit[0]["status"] if hit else "-", "| mode:", hit[0]["mode"] if hit else "-")
p = httpx.get(f"{BASE}/api/positions", timeout=15).json()["positions"]
print("positions rows:", len(p))
assert hit, "order not in ledger"

# kill switch round-trip
r1 = httpx.post(f"{BASE}/api/kill", json={"on": True, "passkey": pk}, timeout=10)
r2 = httpx.post(f"{BASE}/api/order", json={"ticker": tick, "side": "yes", "price": 50, "count": 1, "mode": "live", "passkey": pk, "confirm": "FIRE"}, timeout=10)
r3 = httpx.post(f"{BASE}/api/kill", json={"on": False, "passkey": pk}, timeout=10)
print("kill on:", r1.json(), "| live blocked while killed: HTTP", r2.status_code, r2.json().get("error"), "| kill off:", r3.json())
assert r2.status_code == 423, "kill switch did not block live"

print("MC SMOKE OK")
