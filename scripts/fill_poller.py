# file_id: SOM-PY-0942-v1.0.0 name: fill_poller.py description: Fill poller — syncs exchange fills into the UUID ledger (0x3A7 fills + position updates + realized P&L on sells) every 60s; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [fills, poller, ledger, truth, zero-token] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""fill_poller.py — closes the ledger truth gap.

Every 60s: fetch recent exchange fills -> for any fill not already in
uuid_fills: find its parent order (exchange_order_id), mint the 0x3A7 FILL
child (low-42 = content42(fill_id)), record it, apply to the position.
Sell fills realize P&L immediately: (sell_px - avg_entry) * count.
Assertion on every write: parent order must exist (no orphan fills).
"""
from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import httpx  # noqa: E402
import runlog  # noqa: E402
import sb  # noqa: E402
import uuid_ledger as L  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
POLL_S = 60


def _sign(method, path, ts):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key((ROOT / ".kalshi_key.pem").read_bytes(), password=None)
    sig = key.sign(f"{ts}{method}{path}".encode(),
                   padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                   hashes.SHA256())
    return base64.b64encode(sig).decode()


def kget(path):
    try:
        ts = str(int(time.time() * 1000))
        full = "/trade-api/v2" + path.split("?")[0]
        h = {"KALSHI-ACCESS-KEY": os.getenv("KALSHI_KEY_ID"),
             "KALSHI-ACCESS-SIGNATURE": _sign("GET", full, ts),
             "KALSHI-ACCESS-TIMESTAMP": ts}
        r = httpx.get(KALSHI + path, headers=h, timeout=15)
        return r.json() if "json" in r.headers.get("content-type", "") else {}
    except Exception:
        return {}


def cents(x):
    try:
        return int(round(float(x) * 100))
    except Exception:
        return 0


def sync_once() -> int:
    d = kget("/portfolio/fills?limit=100")
    fills = d.get("fills") or []
    if not fills:
        return 0
    con = sb.sb_conn()
    cur = con.cursor()
    new = 0
    for fl in fills:
        fid = fl.get("fill_id")
        if not fid:
            continue
        cur.execute("SELECT 1 FROM uuid_fills WHERE exchange_fill_id=%s", (fid,))
        if cur.fetchone():
            continue
        xoid = fl.get("order_id")
        cur.execute("SELECT uuid, ticker, side, price_cents FROM uuid_orders WHERE exchange_order_id=%s", (xoid,))
        row = cur.fetchone()
        runlog.assert_event(row is not None, "fills", f"parent order found for fill {fid[:12]}", fill_id=fid, order_id=xoid)
        if not row:
            continue
        ouuid, ticker, oside, oprice = row
        px = cents(fl.get("price_dollars") or fl.get("yes_price_dollars") or 0)
        cnt = int(float(fl.get("count_fp") or 0))
        fee = cents(fl.get("fee_paid_dollars") or 0)
        is_sell = (fl.get("side") or "").lower() == "sell" or (fl.get("action") or "").lower() == "sell"
        mkt = L.mint_market_uuid(ticker)
        side = oside
        # for NO-side buys the exchange price is YES-side; store the NO-side cost
        eff_px = px if (side == "yes" or is_sell) else (100 - px)
        fu = L.mint_fill(ouuid, eff_px, cnt, exchange_fill_id=fid)
        L.record_fill(cur, fu, fee_cents=fee)
        if is_sell:
            # realize against open position average
            cur.execute("SELECT avg_price_cents, net_contracts FROM uuid_positions WHERE ticker=%s AND side=%s", (ticker, side))
            prow = cur.fetchone()
            if prow and prow[1] > 0:
                realized = int(round((px - prow[0]) * min(cnt, prow[1])))
                cur.execute("UPDATE uuid_positions SET net_contracts = net_contracts - %s, realized_pnl_cents = realized_pnl_cents + %s WHERE ticker=%s AND side=%s",
                            (min(cnt, prow[1]), realized, ticker, side))
                cur.execute("DELETE FROM uuid_positions WHERE ticker=%s AND side=%s AND net_contracts <= 0", (ticker, side))
                runlog.log_event("fills", f"SELL synced {ticker[:36]} x{cnt} @ {px}c realized {realized:+d}c", ticker=ticker, realized_c=realized)
        else:
            L.apply_fill_to_position(cur, ticker, side, mkt, eff_px, cnt, fu["ts"])
            runlog.log_event("fills", f"BUY synced {ticker[:36]} {side} x{cnt} @ {eff_px}c fee={fee}c", ticker=ticker)
        con.commit()
        new += 1
    con.close()
    return new


def publish_account():
    """Upsert account snapshot to mc_state so the cloud panel shows live equity."""
    try:
        import json as _json
        bal = kget("/portfolio/balance")
        cash = float(bal.get("balance_dollars") or 0)
        pv = (bal.get("portfolio_value") or 0) / 100
        con = sb.sb_conn()
        con.autocommit = True
        cur = con.cursor()
        cur.execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('account:equity', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (_json.dumps({"cash": cash, "portfolio": pv, "equity": cash + pv, "ts": time.time()}),))
        cur.execute(
            "CREATE TABLE IF NOT EXISTS equity_history (ts TIMESTAMPTZ DEFAULT now(), equity NUMERIC, cash NUMERIC, portfolio NUMERIC)")
        cur.execute("INSERT INTO equity_history (equity, cash, portfolio) VALUES (%s, %s, %s)",
                    (cash + pv, cash, pv))
        con.close()
    except Exception:
        pass


def main():
    fleetlib.acquire_lock("fills")
    runlog.log_event("fills", "fill_poller start", poll_s=POLL_S)
    while True:
        fleetlib.checkin("fills")
        try:
            n = sync_once()
            publish_account()
            if n:
                runlog.log_event("fills", f"sync cycle: {n} new fills", new=n)
        except Exception as e:
            runlog.log_event("fills", f"sync warn {repr(e)[:80]}", kind="warn")
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
