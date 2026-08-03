import sys
from pathlib import Path

import duckdb

sys.path.insert(0, "scripts")
from uuid_service_turboquant import decode_gyst, encode_poly_trade_uuid

ROOT = Path(".")
# build token map
con = duckdb.connect(":memory:")
mfiles = sorted(str(p) for p in (ROOT/"data"/"minted_parquet").glob("markets_*.parquet"))
tok2m = {}
for mf in mfiles:
    try:
        for mid, mu, tok in con.execute(f"SELECT id, gyst_uuid, unnest(json_transform(clob_token_ids,'[\"VARCHAR\"]')) FROM read_parquet('{mf}')").fetchall():
            tok2m[str(tok)] = (str(mid), str(mu))
    except Exception as e:
        print("map skip", mf, e)

tf = sorted(str(p) for p in (ROOT/"data"/"minted_parquet").glob("trades_*.parquet"))[0]
rows = con.execute(f"SELECT transaction_hash, maker_asset_id, taker_asset_id, maker_amount, taker_amount, timestamp FROM read_parquet('{tf}') LIMIT 5").fetchall()
resolved = 0
for tx, ma, ta, mamt, tamt, ts in rows:
    asset = str(ta) if str(ma) in ("0","","None") else str(ma)
    mid, mu = tok2m.get(asset, ("FALLBACK", ""))
    if mid != "FALLBACK":
        resolved += 1
    total = (float(mamt) or 0) + (float(tamt) or 0)
    ts = int(ts) if ts is not None else 1700000000
    price = (float(tamt)/total) if total > 0 else 0.0
    u = encode_poly_trade_uuid(tx, price, timestamp_sec=int(ts), market_uuid=mu or None)
    d = decode_gyst(u)
    print(f"tx={tx[:10]} market_id={mid} sym0x3A2={hex(d.type_code)} price={price:.3f} sig={d.signal_normalized:.3f} uuid={u}")
print(f"\nresolved to real market: {resolved}/5")
print("total token-map size:", len(tok2m))
