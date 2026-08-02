# check outcome of the bot's first BTC15 trade + ledger/session state
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import httpx
import sb

con = sb.sb_conn()
cur = con.cursor()
cur.execute("""SELECT uuid, ticker, side, price_cents, status, exchange_order_id
               FROM uuid_orders WHERE mode='live' ORDER BY created_at DESC LIMIT 5""")
print("=== live orders ===")
for r in cur.fetchall():
    print(f"  {r[1]:28s} {r[2]:3s} {r[3]}c status={r[4]} xid={str(r[5])[:13]}")

cur.execute("SELECT ticker, side, net_count, avg_price_cents, realized_pnl_cents FROM uuid_positions ORDER BY ticker")
print("=== positions ===")
for r in cur.fetchall():
    print(f"  {r[0]:28s} {r[1]:3s} net={r[2]} avg={r[3]} realized={r[4]}c")

cur.execute("SELECT kind, msg, ts FROM mc_log ORDER BY id DESC LIMIT 6") if False else None
con.close()

# check market result from exchange
r = httpx.get("https://api.elections.kalshi.com/trade-api/v2/markets/KXBTC15M-26AUG021515-15",
              headers={"Accept-Encoding": "identity"}, timeout=15)
m = r.json().get("market", {})
print("=== exchange market state ===")
print("  status:", m.get("status"), "| result:", m.get("result"), "| last:", m.get("last_price_dollars"))
