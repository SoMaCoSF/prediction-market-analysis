# income round 2: ledger settle write-back for the 4 wins + fire momentum sleeve on current window
import hashlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import httpx
import sb
import uuid_ledger as L

MC = "http://127.0.0.1:8420"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
PK = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()

# 1) ledger write-back: settle the 4 winning positions (result=yes => settle at 100)
wins = {"KXXRP15M-26AUG021545-45": 25, "KXDOGE15M-26AUG021545-45": 42,
        "KXSOL15M-26AUG021545-45": 44, "KXETH15M-26AUG021545-45": 47}
con = sb.sb_conn()
cur = con.cursor()
for t, entry in wins.items():
    cur.execute("SELECT uuid FROM uuid_orders WHERE ticker=%s AND mode='live' AND status='submitted' LIMIT 1", (t,))
    row = cur.fetchone()
    if not row:
        print(f"  {t}: no ledger order, skip")
        continue
    mkt = L.mint_market_uuid(t)
    fu = L.mint_fill(row[0], entry, 1, exchange_fill_id=f"settle-backfill:{t}")
    L.record_fill(cur, fu, fee_cents=2)
    L.apply_fill_to_position(cur, t, "yes", mkt, entry, 1, fu["ts"])
    L.settle(cur, t, mkt, 100)   # result=yes -> YES settles at 100
    con.commit()
    cur.execute("SELECT realized_pnl_cents FROM uuid_positions WHERE ticker=%s AND side='yes'", (t,))
    print(f"  {t}: realized {cur.fetchone()[0]}c written to ledger")
cur.execute("SELECT coalesce(sum(realized_pnl_cents),0) FROM uuid_positions")
print("ledger total realized:", cur.fetchone()[0], "c")
con.close()

# 2) fire round 2: current 15M window, drift read per asset
def drift(cx, pair):
    d = cx.get(f"https://api.kraken.com/0/public/Ticker?pair={pair}", timeout=10).json()["result"]
    k = next(iter(d))
    return (float(d[k]["c"][0]) - float(d[k]["o"])) / float(d[k]["o"]) * 100

def fire(ticker, side, price):
    r = httpx.post(f"{MC}/api/order", json={"ticker": ticker, "side": side, "price": price,
                   "count": 1, "mode": "live", "passkey": PK, "confirm": "FIRE"}, timeout=30)
    d = r.json()
    ack = d.get("ack") or {}
    return d.get("ok"), float(ack.get("fill_count") or 0), ack.get("average_fill_price"), d.get("error")

print("\n=== ROUND 2: current window ===")
with httpx.Client(headers={"Accept-Encoding": "identity"}) as cx:
    for series, pair in [("KXBTC15M", "XBTUSD"), ("KXETH15M", "ETHUSD"), ("KXSOL15M", "SOLUSD"),
                         ("KXXRP15M", "XRPUSD"), ("KXDOGE15M", "DOGEUSD")]:
        r = cx.get(f"{KALSHI}/markets", params={"limit": 5, "status": "open", "series_ticker": series}, timeout=15)
        m = None
        for mm in r.json().get("markets", []):
            ya = float(mm.get("yes_ask_dollars") or 0)
            if 0 < ya < 1:
                from datetime import datetime
                ttl = datetime.fromisoformat(mm["close_time"].replace("Z", "+00:00")).timestamp() - time.time()
                if ttl > 150:
                    m = {"ticker": mm["ticker"], "ya": round(ya * 100), "yb": round(float(mm.get("yes_bid_dollars") or 0) * 100), "ttl": ttl}
                    break
        if not m:
            print(f"  {series}: no tradeable window (close < 150s or no book)")
            continue
        d = drift(cx, pair)
        if d >= 0.15 and m["ya"] <= 60:
            side, price = "yes", m["ya"]
        elif d <= -0.15 and (100 - m["yb"]) <= 60:
            side, price = "no", 100 - m["yb"]
        else:
            print(f"  {series}: drift {d:+.2f}% flat, skip (ya={m['ya']} ttl={m['ttl']:.0f}s)")
            continue
        ok, filled, avg, err = fire(m["ticker"], side, price)
        print(f"  {pair} {d:+.2f}% -> {side.upper()} {price}c {m['ticker'][:40]} | "
              f"{'FILL@'+str(avg) if filled else ('RESTING' if ok else 'REJ '+str(err)[:40])}")
        time.sleep(0.4)
