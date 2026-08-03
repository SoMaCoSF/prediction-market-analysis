# cross-verify: Python GYST mint vs JS GYST mint (must be byte-identical)
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uuid_ledger as L

TS = 1_800_000_000
mkt = L.mint_market_uuid("KXMLB-26-LAD", ts=TS)
order = L.mint_order("KXMLB-26-LAD", "yes", 41, 1, parent_uuid=mkt, ts=TS)
ack = L.mint_ack(order["uuid"], "a410c673-6cad-4747-96d0-f8ac5fca5145", 40.9, ts_ms=1_800_000_060_000)
print(json.dumps({
    "market": mkt,
    "order_uuid": order["uuid"],
    "order_hi": str(order["uuid_hi"]),
    "order_lo": str(order["uuid_lo"]),
    "client_order_id": order["client_order_id"],
    "ack_uuid": ack["uuid"],
    "ack_hi": str(ack["uuid_hi"]),
    "ack_lo": str(ack["uuid_lo"]),
}))
