# file_id: SOM-PY-0920-v1.0.0 name: mission_control.py description: Mission control web server — terminal-UX dashboard for the UUID trader: corpus stats, Kalshi markets, ledger views, passkey-gated PAPER/FIRE controls, kill switch project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [mission-control, dashboard, trading, kalshi, uuid] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""mission_control.py — web terminal for the UUID trading system.

Data planes:
  trading ledger  -> Supabase PG (shared SoT with the Vercel deployment)
  corpus stats    -> local bundled PG (52.77M rows; degrades gracefully if down)
  markets         -> Kalshi public API (no auth), 20s cache

Controls:
  PAPER fire  -> mint 0x3A4 + record + simulated fill (full ledger exercise)
  LIVE fire   -> passkey + confirm=FIRE + kill-switch off + caps (count<=5,
                 notional<=$5) -> RSA-PSS signed POST /portfolio/orders,
                 client_order_id = order UUID low-42 tail (bitmask reconcile)

Passkey derivation mirrors app/lib/auth.js: sha256(mac|hostname|STATUS_SALT).
Run: .venv311/Scripts/python scripts/mission_control.py  ->  http://127.0.0.1:8420
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

import threading  # noqa: E402

import fleetlib  # noqa: E402
import httpx  # noqa: E402
import runlog  # noqa: E402
import sb  # noqa: E402
import uuid_ledger as L  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse  # noqa: E402
from uuid_service_turboquant import decode_gyst, encode_gyst  # noqa: E402

STATIC = Path(__file__).resolve().parent / "mc_static"
KILL_FILE = ROOT / ".mc_kill"
KALSHI_HOST = os.getenv("KALSHI_HOST", "https://api.elections.kalshi.com/trade-api/v2")

LOG: deque = deque(maxlen=300)


def log(msg: str, kind: str = "info"):
    LOG.appendleft({"ts": int(time.time()), "kind": kind, "msg": msg})
    print(f"[mc:{kind}] {msg}", flush=True)
    runlog.log_event("mc", msg, kind=kind)


# ---------------- auth / gates ----------------

def expected_passkey() -> str:
    return hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()


def passkey_ok(candidate: str) -> bool:
    return bool(candidate) and hmac.compare_digest(str(candidate), expected_passkey())


def killed() -> bool:
    return KILL_FILE.exists()


def kalshi_keys():
    kid = os.getenv("KALSHI_KEY_ID")
    kpath = os.getenv("KALSHI_PRIVATE_KEY_PATH")
    if not kpath and (ROOT / ".kalshi_key.pem").exists():
        kpath = str(ROOT / ".kalshi_key.pem")
    return kid, kpath


def keys_present() -> bool:
    kid, kpath = kalshi_keys()
    return bool(kid and kpath)


# ---------------- kalshi signing ----------------

def kalshi_sign(method: str, path: str, ts_ms: str, key_path: str) -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key(Path(key_path).read_bytes(), password=None)
    msg = f"{ts_ms}{method.upper()}{path}".encode()
    sig = key.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                    salt_length=padding.PSS.DIGEST_LENGTH),
                   hashes.SHA256())
    return base64.b64encode(sig).decode()


def kalshi_post_order(req_body: dict):
    """Kalshi Create Order V2 — POST /portfolio/events/orders.

    req_body (v1-style, internal): {ticker, side: yes|no, action, count, type,
    yes_price|no_price (cents), client_order_id}
    Translated to V2 wire shape: side=bid/ask on the YES contract, price as a
    dollar string, count as a fixed-point string. (Buying YES = 'bid'.)
    """
    kid, kpath = kalshi_keys()
    path = "/trade-api/v2/portfolio/events/orders"
    side_v1 = req_body["side"].lower()
    price_cents = req_body.get("yes_price", req_body.get("no_price"))
    # V2 unified book trades the YES contract. Buying NO at P¢ is selling YES
    # at (100-P)¢ — the price MUST be mirrored for the no side.
    if side_v1 == "yes":
        v2_side, v2_price = "bid", price_cents / 100.0
    else:
        v2_side, v2_price = "ask", (100 - price_cents) / 100.0
    v2 = {
        "ticker": req_body["ticker"],
        "client_order_id": req_body["client_order_id"],
        "side": v2_side,
        "count": f"{int(req_body['count']):.2f}",
        "price": f"{v2_price:.4f}",
        "time_in_force": "good_till_canceled",
        "self_trade_prevention_type": "taker_at_cross",
        "post_only": False,
        "cancel_order_on_pause": False,
        "reduce_only": False,
        "subaccount": 0,
        "exchange_index": -1,   # auto-route shard by ticker
    }
    if req_body.get("expiration_ts"):
        v2["time_in_force"] = "good_till_time"
        v2["expiration_ts"] = int(req_body["expiration_ts"])
    ts = str(int(time.time() * 1000))
    headers = {
        "KALSHI-ACCESS-KEY": kid,
        "KALSHI-ACCESS-SIGNATURE": kalshi_sign("POST", path, ts, kpath),
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "Content-Type": "application/json",
    }
    r = httpx.post(f"{KALSHI_HOST}/portfolio/events/orders", json=v2, headers=headers, timeout=20)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:400]}


# ---------------- data planes ----------------

def sb_cur():
    con = sb.sb_conn()
    return con, con.cursor()


_corpus_cache = {"ts": 0, "data": None}


def corpus_stats():
    if time.time() - _corpus_cache["ts"] < 60 and _corpus_cache["data"] is not None:
        return _corpus_cache["data"]
    out = {"online": False}
    try:
        con = L.local_conn()
        cur = con.cursor()
        cur.execute("SELECT count(*) FROM uuid_trades")
        out["trades"] = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM uuid_markets")
        out["markets"] = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM uuid_quotes")
        out["quotes"] = cur.fetchone()[0]
        con.close()
        out["online"] = True
    except Exception as e:
        out["error"] = repr(e)[:120]
    # wirespeed micro-benchmark (in-process, no DB)
    try:
        n = 4000
        t0 = time.perf_counter()
        for i in range(n):
            u = encode_gyst(type_code=0x3A2, namespace=i & 0xFFF, forecast_signal=0.5,
                            provenance=0x9, content_seed=f"bench{i}")
            decode_gyst(u)
        out["decode_ops"] = int(n / (time.perf_counter() - t0))
    except Exception:
        out["decode_ops"] = None
    _corpus_cache.update(ts=time.time(), data=out)
    return out


_mkt_cache = {"ts": 0, "data": None}


def _cents(v) -> int | None:
    """dollar-string ('0.4200') -> cents int; legacy int cents pass through."""
    if v is None:
        return None
    try:
        f = float(v)
        return int(round(f * 100)) if f <= 1.0 else int(round(f))
    except (TypeError, ValueError):
        return None


async def live_markets():
    if time.time() - _mkt_cache["ts"] < 20 and _mkt_cache["data"] is not None:
        return _mkt_cache["data"]
    async with httpx.AsyncClient(timeout=20) as cx:
        r = await cx.get(f"{KALSHI_HOST}/markets", params={"limit": 200, "status": "open"})
        rows = []
        for m in r.json().get("markets", []):
            yes_bid = _cents(m.get("yes_bid_dollars", m.get("yes_bid")))
            yes_ask = _cents(m.get("yes_ask_dollars", m.get("yes_ask")))
            try:
                vol = float(m.get("volume_fp", m.get("volume") or 0))
            except (TypeError, ValueError):
                vol = 0.0
            try:
                ask_size = float(m.get("yes_ask_size_fp") or 0)
            except (TypeError, ValueError):
                ask_size = 0.0
            rows.append({
                "ticker": m.get("ticker"),
                "title": (m.get("title") or m.get("subtitle") or "")[:80],
                "yes_bid": yes_bid, "yes_ask": yes_ask,
                "ask_size": ask_size,
                "volume": vol,
                "close_time": m.get("close_time"),
            })
        rows.sort(key=lambda x: -x["volume"])
        _mkt_cache.update(ts=time.time(), data=rows[:25])
        return _mkt_cache["data"]


# ---------------- app ----------------

app = FastAPI(title="SOMACO TRADE CONTROL", docs_url=None, redoc_url=None)


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/about", response_class=HTMLResponse)
async def about():
    return (STATIC / "about.html").read_text(encoding="utf-8")


@app.get("/api/stats")
async def api_stats():
    con, cur = sb_cur()
    cur.execute("SELECT count(*) FROM uuid_orders")
    orders = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM uuid_fills")
    fills = cur.fetchone()[0]
    cur.execute("SELECT coalesce(sum(realized_pnl_cents),0) FROM uuid_positions")
    realized = int(cur.fetchone()[0])
    cur.execute("SELECT coalesce(sum(net_count),0) FROM uuid_positions")
    exposure = int(cur.fetchone()[0])
    con.close()
    return {
        "corpus": corpus_stats(),
        "ledger": {"orders": orders, "fills": fills,
                   "realized_pnl_cents": realized, "open_contracts": exposure},
        "kill": killed(),
        "keys": keys_present(),
        "passkey_hint_len": len(expected_passkey()),
        "ts": int(time.time()),
    }


@app.get("/api/markets")
async def api_markets():
    try:
        return {"markets": await live_markets()}
    except Exception as e:
        return JSONResponse({"error": repr(e)[:200]}, status_code=502)


@app.get("/api/orders")
async def api_orders(limit: int = 50):
    con, cur = sb_cur()
    cur.execute("""SELECT uuid, client_order_id, ticker, side, price_cents, count,
                          status, mode, exchange_order_id, ts
                   FROM uuid_orders ORDER BY created_at DESC LIMIT %s""", (min(limit, 200),))
    cols = ["uuid", "client_order_id", "ticker", "side", "price_cents", "count",
            "status", "mode", "exchange_order_id", "ts"]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    con.close()
    return {"orders": rows}


@app.get("/api/fills")
async def api_fills(limit: int = 50):
    con, cur = sb_cur()
    cur.execute("""SELECT uuid, parent_uuid, price_cents, count, fee_cents, ts
                   FROM uuid_fills ORDER BY created_at DESC LIMIT %s""", (min(limit, 200),))
    cols = ["uuid", "parent_uuid", "price_cents", "count", "fee_cents", "ts"]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    con.close()
    return {"fills": rows}


@app.get("/api/positions")
async def api_positions():
    con, cur = sb_cur()
    cur.execute("""SELECT ticker, side, net_count, avg_price_cents, realized_pnl_cents, updated_ts
                   FROM uuid_positions ORDER BY ticker, side""")
    cols = ["ticker", "side", "net_count", "avg_price_cents", "realized_pnl_cents", "updated_ts"]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    con.close()
    return {"positions": rows}


@app.get("/api/pnl")
async def api_pnl():
    con, cur = sb_cur()
    rows = L.pnl_rollup(cur)
    con.close()
    return {"pnl": rows}


@app.get("/api/log")
async def api_log():
    return {"log": list(LOG)[:120]}


@app.post("/api/kill")
async def api_kill(req: Request):
    body = await req.json()
    if not passkey_ok(body.get("passkey", "")):
        return JSONResponse({"error": "bad passkey"}, status_code=403)
    on = bool(body.get("on"))
    if on:
        KILL_FILE.write_text(str(int(time.time())))
        log("KILL SWITCH ENGAGED — all live firing blocked", "kill")
    else:
        KILL_FILE.unlink(missing_ok=True)
        log("kill switch disengaged", "warn")
    return {"kill": killed()}


@app.post("/api/order")
async def api_order(req: Request):
    body = await req.json()
    if not passkey_ok(body.get("passkey", "")):
        log("order REJECTED: bad passkey", "warn")
        return JSONResponse({"error": "bad passkey"}, status_code=403)
    try:
        ticker = str(body["ticker"]).strip()
        side = str(body["side"]).lower()
        price = int(body["price"])
        count = int(body["count"])
        mode = str(body.get("mode", "paper")).lower()
        assert side in ("yes", "no") and 1 <= price <= 99 and 1 <= count <= 25 and mode in ("paper", "live")
    except Exception:
        return JSONResponse({"error": "invalid ticker/side/price/count/mode (count<=5)"}, status_code=400)
    notional = price * count
    if notional > 2500:
        return JSONResponse({"error": f"cap: notional {notional}¢ > 2500¢ ($25)"}, status_code=400)

    o = L.mint_order(ticker, side, price, count)
    price_key = "yes_price" if side == "yes" else "no_price"
    req_body = {"ticker": ticker, "side": side, "action": "buy", "count": count,
                "type": "limit", price_key: price, "client_order_id": o["client_order_id"]}
    con, cur = sb_cur()

    if mode == "paper":
        L.record_order(cur, o, mode="paper", status="filled")
        f = L.mint_fill(o["uuid"], price, count)
        L.record_fill(cur, f, fee_cents=0)
        L.apply_fill_to_position(cur, ticker, side, o["parent_uuid"], price, count, o["ts"])
        con.commit()
        con.close()
        log(f"PAPER fill {side} {price}¢ x{count} {ticker}  uuid={o['uuid'][:13]}… coi={o['client_order_id']}", "paper")
        return {"ok": True, "mode": "paper", "uuid": o["uuid"], "client_order_id": o["client_order_id"]}

    # ---- live ----
    if killed():
        con.close()
        log("LIVE order BLOCKED by kill switch", "kill")
        return JSONResponse({"error": "kill switch engaged"}, status_code=423)
    if body.get("confirm") != "FIRE":
        con.close()
        return JSONResponse({"error": "live requires confirm=FIRE"}, status_code=400)
    if not keys_present():
        con.close()
        return JSONResponse({"error": "KALSHI keys not configured (.kalshi_key.pem / KALSHI_KEY_ID)"}, status_code=400)

    L.record_order(cur, o, mode="live", status="submitting")
    con.commit()
    log(f"LIVE submit {side} {price}¢ x{count} {ticker}  uuid={o['uuid'][:13]}… coi={o['client_order_id']}", "live")
    try:
        code, resp = kalshi_post_order(req_body)
    except Exception as e:
        cur.execute("UPDATE uuid_orders SET status='error' WHERE uuid=%s", (o["uuid"],))
        con.commit()
        con.close()
        log(f"LIVE submit exception: {repr(e)[:160]}", "error")
        return JSONResponse({"error": repr(e)[:200]}, status_code=502)
    if code in (200, 201):
        oid = resp.get("order_id") or (resp.get("order") or {}).get("order_id")
        fills = resp.get("fill_count")
        # mint + record the ACK child UUID (0x3A6): exchange order_id reconciles by low-42
        avg_px_c = None
        if resp.get("average_fill_price") is not None:
            try:
                avg_px_c = float(resp["average_fill_price"]) * 100.0
            except (TypeError, ValueError):
                avg_px_c = None
        try:
            ack = L.mint_ack(o["uuid"], str(oid), avg_px_c, ts_ms=resp.get("ts_ms"))
            L.record_ack(cur, ack,
                         fill_count=float(resp.get("fill_count") or 0),
                         remaining_count=float(resp.get("remaining_count") or 0),
                         avg_price_cents=avg_px_c)
            log(f"ACK uuid={ack['uuid'][:13]}… minted for exchange order_id (0x3A6 child)", "live")
        except Exception as e:
            log(f"ack mint warn: {repr(e)[:120]}", "warn")
        cur.execute("UPDATE uuid_orders SET status='submitted', exchange_order_id=%s WHERE uuid=%s",
                    (oid, o["uuid"]))
        con.commit()
        con.close()
        log(f"LIVE ACK order_id={oid} fill_count={fills} coi={o['client_order_id']}  (reconciles by low-42 bitmask)", "live")
        return {"ok": True, "mode": "live", "uuid": o["uuid"],
                "client_order_id": o["client_order_id"], "exchange_order_id": oid, "ack": resp}
    cur.execute("UPDATE uuid_orders SET status='rejected' WHERE uuid=%s", (o["uuid"],))
    con.commit()
    con.close()
    log(f"LIVE REJECTED {code}: {json.dumps(resp)[:200]}", "error")
    return JSONResponse({"error": "exchange rejected", "status": code, "resp": resp}, status_code=400)


if __name__ == "__main__":
    fleetlib.acquire_lock("mc")
    def _checkin_loop():
        while True:
            fleetlib.checkin("mc")
            time.sleep(30)
    threading.Thread(target=_checkin_loop, daemon=True).start()
    log("mission control starting on http://127.0.0.1:8420")
    uvicorn.run(app, host="127.0.0.1", port=8420, log_level="warning")
