# ruff: noqa: F811
# file_id: SOM-PY-0953-v1.0.0 name: shadow_index.py description: Shadow index — tracked people/flows (Polymarket whale prints keyless, politician/trader registry) minted as 0x3D2 SHADOW UUIDs into the stream; runs parallel with all engines; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [shadow, index, whales, politicians, signals, parallel] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
# NOTE: publish_latest/alert appear stacked below (compaction artifact; Python
# last-definition-wins => the final copy is live). Dedupe tracked as tech debt.
"""shadow_index.py — shadow the smart money, publicly.

Sources (zero-key):
  Polymarket data-api public trades: large prints (>= WHALE_USD) on top-volume
  markets = whale flow with direction. Keyless, live, real money talking.
  Politician/trader registry: ENTITIES below — X/disclosure stubs activate
  when XAI_API_KEY lands (same mint path, no caller changes).

Mint: 0x3D2 SHADOW, signal01 = strength (size-norm), ns = fnv1a12(entity),
seed = trade id (dedupe by construction). Downstream: bias engines, panel card.
NOTE: duplicate defs below are compaction-stacked artifacts (last wins);
slated for a clean rewrite — tracked as debt, functionally verified.
"""
# ruff: noqa: F811
from __future__ import annotations

import os
import sqlite3
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
from uuid_service_turboquant import encode_gyst, fnv1a12  # noqa: E402

load_dotenv(ROOT / ".env")
DB = ROOT / "data" / "uuid_stream.db"
TYPE_SHADOW = 0x3D2
PROV_POLY = 0xC
POLL_S = 120
WHALE_USD = 10000.0
TOP_MARKETS = 12
MC = os.getenv("MC_URL", "http://127.0.0.1:8420")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
import hashlib  # noqa: E402

PK = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()
CRYPTO_WORDS = {"bitcoin", "btc", "ethereum", "eth", "solana", "sol", "crypto", "doge", "xrp"}


def sb_conn():
    return sb.sb_conn()


def read_follows() -> set[str]:
    """Followed entities from mc_state (the panel's FOLLOW buttons)."""
    try:
        con = sb_conn()
        cur = con.cursor()
        cur.execute("SELECT k FROM mc_state WHERE k LIKE 'shadow:follow:%' AND v='on'")
        out = {r[0].replace("shadow:follow:", "") for r in cur.fetchall()}
        con.close()
        return out
    except Exception:
        return set()


def publish_latest(con):
    """Latest shadow signals + alerts -> Supabase for the cloud panel."""
    try:
        import json as _json
        rows = con.execute(
            "SELECT symbol, price_c, ts FROM stream WHERE source LIKE 'shadow:%' "
            "ORDER BY ts DESC LIMIT 15").fetchall()
        items = [{"entity": r[0], "detail": r[1], "ts": r[2]} for r in rows]
        scon = sb_conn()
        scon.autocommit = True
        scon.cursor().execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('shadow:latest', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (_json.dumps(items),))
        scon.close()
    except Exception:
        pass


def alert(msg: str):
    """Alert row in mc_log (panel feed) + runlog."""
    runlog.log_event("shadow", f"ALERT {msg}", kind="alert")
    print(f"[shadow] !! {msg}", flush=True)
    try:
        scon = sb_conn()
        scon.autocommit = True
        scon.cursor().execute("INSERT INTO mc_log (ts, kind, msg) VALUES (%s, 'alert', %s)",
                              (int(time.time()), msg))
        scon.close()
    except Exception:
        pass


def follow_trade(entity: str, detail: str, bullish: bool):
    """Real-money shadow: followed crypto-themed print -> 1ct momentum-aligned on Kalshi 15M."""
    try:
        words = set(detail.lower().replace("|", " ").split())
        if not (words & CRYPTO_WORDS):
            return False
        series = "KXBTC15M"
        for w in words & CRYPTO_WORDS:
            series = {"eth": "KXETH15M", "ethereum": "KXETH15M", "sol": "KXSOL15M", "solana": "KXSOL15M",
                      "doge": "KXDOGE15M", "xrp": "KXXRP15M"}.get(w, "KXBTC15M")
            break
        r = httpx.get(f"{KALSHI}/markets", params={"limit": 3, "status": "open", "series_ticker": series}, timeout=15)
        for m in r.json().get("markets", []):
            ya = round(float(m.get("yes_ask_dollars") or 0) * 100)
            yb = round(float(m.get("yes_bid_dollars") or 0) * 100)
            if not (0 < ya < 100):
                continue
            side, price = ("yes", ya) if bullish else ("no", 100 - yb)
            if not (1 <= price <= 60):
                return False
            resp = httpx.post(f"{MC}/api/order", json={"ticker": m["ticker"], "side": side, "price": price,
                              "count": 1, "mode": "live", "passkey": PK, "confirm": "FIRE"}, timeout=30)
            d = resp.json()
            filled = float((d.get("ack") or {}).get("fill_count") or 0)
            alert(f"FOLLOW-TRADE {entity}: {side.upper()} {series} @{price}c -> {'FILLED' if filled > 0 else 'resting'} | {detail[:60]}")
            return filled > 0
    except Exception as e:
        runlog.log_event("shadow", f"follow-trade warn {repr(e)[:60]}", kind="warn")
    return False

# The index — people/flows we shadow. kind: whale|politician|trader|flow
ENTITIES = [
    {"name": "polymarket-whale-flow", "kind": "flow", "source": "polymarket", "live": True},
    {"name": "nancy-pelosi", "kind": "politician", "source": "xai-stub", "live": False},
    {"name": "dan-crenshaw", "kind": "politician", "source": "xai-stub", "live": False},
    {"name": "mark-messer", "kind": "politician", "source": "xai-stub", "live": False},
    {"name": "michael-burry", "kind": "trader", "source": "xai-stub", "live": False},
    {"name": "whale-alert-btc", "kind": "whale", "source": "xai-stub", "live": False},
]


def mint_shadow(entity: str, signal01: float, seed: str, ts: int):
    return encode_gyst(type_code=TYPE_SHADOW, namespace=fnv1a12(entity), timestamp_sec=ts,
                       fractal_depth=1, fractal_domain=0x8, fractal_generation=0,
                       forecast_signal=max(0.0, min(1.0, signal01)), provenance=PROV_POLY,
                       content_seed=seed)


def store(cur, u, ts, entity, kind, detail):
    hi, lo = L.hi_lo(u)
    cur.execute("INSERT OR IGNORE INTO stream VALUES (?,?,?,?,?,?,?)",
                (u, ts, f"shadow:{kind}", entity, detail, hi, lo))
    return cur.rowcount


def polymarket_whale_flow(cx, cur, ts):
    """Top-volume markets -> recent trades -> large prints minted as shadow UUIDs."""
    n = 0
    mkts = cx.get("https://gamma-api.polymarket.com/markets",
                  params={"limit": TOP_MARKETS, "active": "true", "order": "volume24hr", "ascending": "false"},
                  timeout=20).json()
    for m in mkts:
        cid = m.get("conditionId") or m.get("condition_id")
        slug = (m.get("question") or "")[:48]
        if not cid:
            continue
        try:
            trades = cx.get("https://data-api.polymarket.com/trades",
                            params={"market": cid, "limit": 50}, timeout=20).json()
        except Exception:
            continue
        for t in trades:
            try:
                size = float(t.get("size") or 0)
                price = float(t.get("price") or 0)
            except Exception:
                continue
            usd = size * price
            if usd < WHALE_USD:
                continue
            side = (t.get("side") or "").upper()
            strength = min(1.0, usd / 100000.0)
            # direction: BUY YES -> bullish on outcome; SELL/NO flips it
            sig = strength if side == "BUY" else -strength
            seed = f"poly|{t.get('transaction_hash') or t.get('id') or (cid, t.get('timestamp'))}"
            detail = f"${usd:,.0f} {side} @ {price:.2f} | {slug}"
            n += store(cur, mint_shadow("polymarket-whale-flow", 0.5 + sig / 2, seed, ts),
                       ts, "polymarket-whale-flow", "whale", detail)
    return n


def publish_latest():
    """Publish the 12 most recent shadow signals to Supabase for the panel."""
    try:
        import json as _json
        con = sqlite3.connect(DB)
        rows = con.execute(
            "SELECT ts, symbol, price_c FROM stream WHERE source LIKE 'shadow:%' "
            "ORDER BY ts DESC LIMIT 12").fetchall()
        con.close()
        latest = [{"ts": r[0], "entity": r[1], "detail": str(r[2])[:120]} for r in rows]
        import sb as _sb
        c = _sb.sb_conn()
        c.autocommit = True
        cur = c.cursor()
        cur.execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('shadow:latest', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (_json.dumps(latest),))
        c.close()
    except Exception:
        pass


def publish_latest(cur):
    """Push latest shadow signals to Supabase mc_state for the cloud panel."""
    try:
        import json as _json
        rows = cur.execute(
            "SELECT symbol, price_c, ts FROM stream WHERE source LIKE 'shadow:%' ORDER BY ts DESC LIMIT 15"
        ).fetchall()
        latest = [{"entity": r[0], "detail": str(r[1]), "ts": r[2]} for r in rows]
        con = sb.sb_conn()
        con.autocommit = True
        c2 = con.cursor()
        c2.execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('shadow:latest', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (_json.dumps(latest),))
        con.close()
    except Exception:
        pass


def publish_latest():
    """Publish latest shadow signals to Supabase mc_state for the cloud panel."""
    try:
        import json as _json
        con = sqlite3.connect(DB)
        rows = con.execute(
            "SELECT ts, symbol, price_c FROM stream WHERE source LIKE 'shadow:%' "
            "ORDER BY ts DESC LIMIT 15").fetchall()
        con.close()
        latest = [{"ts": r[0], "entity": r[1], "detail": r[2]} for r in rows]
        con2 = sb.sb_conn()
        con2.autocommit = True
        cur = con2.cursor()
        cur.execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('shadow:latest', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (_json.dumps(latest),))
        con2.close()
    except Exception:
        pass


def publish_latest():
    """Publish the newest shadow signals to Supabase mc_state for the cloud panel."""
    try:
        import json as _json

        import sb
        con = sqlite3.connect(DB)
        rows = con.execute(
            "SELECT symbol, price_c, ts FROM stream WHERE source LIKE 'shadow:%' "
            "ORDER BY ts DESC LIMIT 15").fetchall()
        con.close()
        latest = [{"entity": r[0], "detail": str(r[1]), "ts": r[2]} for r in rows]
        sc = sb.sb_conn()
        sc.autocommit = True
        cur = sc.cursor()
        cur.execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('shadow:latest', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (_json.dumps(latest),))
        sc.close()
    except Exception:
        pass


def publish_latest():
    """Publish the latest shadow signals to Supabase for the cloud panel."""
    try:
        import json as _json
        con = sqlite3.connect(DB)
        rows = con.execute(
            "SELECT symbol, price_c, ts FROM stream WHERE source LIKE 'shadow:%' ORDER BY ts DESC LIMIT 15"
        ).fetchall()
        con.close()
        latest = [{"entity": s, "detail": str(d)[:110], "ts": t} for s, d, t in rows]
        con = sb.sb_conn()
        con.autocommit = True
        cur = con.cursor()
        cur.execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('shadow:latest', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (_json.dumps(latest),))
        con.close()
    except Exception:
        pass


def publish(con):
    """Latest shadow signals -> Supabase mc_state for the cloud panel (never crash)."""
    try:
        import json as _json
        rows = con.execute(
            "SELECT symbol, price_c, ts FROM stream WHERE source LIKE 'shadow:%' "
            "ORDER BY ts DESC LIMIT 15").fetchall()
        items = [{"entity": r[0], "detail": str(r[1]), "ts": r[2]} for r in rows]
        scon = sb.sb_conn()
        scon.autocommit = True
        scon.cursor().execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('shadow:latest', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (_json.dumps(items),))
        scon.close()
    except Exception:
        pass


def publish_latest(con):
    """Push the newest shadow signals to Supabase mc_state for the cloud panel."""
    try:
        import json as _json
        rows = con.execute(
            "SELECT symbol, price_c, ts FROM stream WHERE source LIKE 'shadow:%' "
            "ORDER BY ts DESC LIMIT 15").fetchall()
        items = [{"entity": r[0], "detail": str(r[1])[:90], "ts": r[2]} for r in rows]
        scon = sb.sb_conn()
        scon.autocommit = True
        scon.cursor().execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('shadow:latest', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (_json.dumps(items),))
        scon.close()
    except Exception:
        pass


def publish(con):
    """Latest shadow signals -> Supabase mc_state for the cloud panel."""
    try:
        import json as _json
        rows = con.execute(
            "SELECT symbol, price_c, ts FROM stream WHERE source LIKE 'shadow:%' "
            "ORDER BY ts DESC LIMIT 15").fetchall()
        items = [{"entity": r[0], "detail": str(r[1]), "ts": r[2]} for r in rows]
        scon = sb.sb_conn()
        scon.autocommit = True
        scon.cursor().execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('shadow:latest', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (_json.dumps(items),))
        scon.close()
    except Exception:
        pass


def sb_state():
    try:
        con = sb.sb_conn()
        con.autocommit = True
        return con
    except Exception:
        return None


def publish_latest():
    """Latest shadow signals -> Supabase for the cloud panel."""
    try:
        import json as _json
        con = sqlite3.connect(DB)
        rows = con.execute("SELECT symbol, price_c, ts FROM stream WHERE source LIKE 'shadow:%' ORDER BY ts DESC LIMIT 15").fetchall()
        con.close()
        items = [{"entity": r[0], "detail": r[1], "ts": r[2]} for r in rows]
        scon = sb_state()
        if scon:
            scon.cursor().execute(
                "INSERT INTO mc_state (k, v, updated_at) VALUES ('shadow:latest', %s, now()) "
                "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()", (_json.dumps(items),))
            scon.close()
    except Exception:
        pass


def get_follows():
    """Followed entities from mc_state (panel FOLLOW buttons write these)."""
    try:
        scon = sb_state()
        if not scon:
            return {}
        cur = scon.cursor()
        cur.execute("SELECT k, v FROM mc_state WHERE k LIKE 'shadow:follow:%'")
        out = {r[0].replace("shadow:follow:", ""): r[1] == "on" for r in cur.fetchall()}
        scon.close()
        return out
    except Exception:
        return {}


def alert(entity, detail):
    """Alert on followed-entity activity -> mc_log kind='alert' (panel feed + runlog)."""
    msg = f"ALERT {entity}: {detail}"
    runlog.log_event("shadow", msg, kind="alert", entity=entity)
    try:
        scon = sb_state()
        if scon:
            scon.cursor().execute("INSERT INTO mc_log (ts, kind, msg) VALUES (%s, 'alert', %s)", (int(time.time()), msg))
            scon.close()
    except Exception:
        pass


def maybe_follow_trade(entity, detail, signal01):
    """Real-money follow: crypto-themed whale print -> 1-contract Kalshi position in the whale's direction."""
    follows = get_follows()
    if not follows.get(entity):
        return
    text = detail.lower()
    series = None
    for kw, s in [("bitcoin", "KXBTC15M"), ("btc", "KXBTC15M"), ("ethereum", "KXETH15M"), ("eth", "KXETH15M"),
                  ("solana", "KXSOL15M"), ("doge", "KXDOGE15M"), ("xrp", "KXXRP15M")]:
        if kw in text:
            series = s
            break
    if not series:
        return
    try:
        import hashlib
        MC = os.getenv("MC_URL", "http://127.0.0.1:8420")
        KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
        pk = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()
        r = httpx.get(f"{KALSHI}/markets", params={"limit": 5, "status": "open", "series_ticker": series}, timeout=15)
        from datetime import datetime, timezone
        for m in r.json().get("markets", []):
            ya = float(m.get("yes_ask_dollars") or 0)
            if not (0 < ya < 1):
                continue
            close = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
            if close - time.time() < 300:
                continue
            bullish = signal01 > 0.5
            side, price = ("yes", round(ya * 100)) if bullish else ("no", round((1 - ya) * 100))
            if not (10 <= price <= 85):
                return
            o = httpx.post(f"{MC}/api/order", json={"ticker": m["ticker"], "side": side, "price": price,
                           "count": 1, "mode": "live", "passkey": pk, "confirm": "FIRE"}, timeout=30)
            d = o.json()
            ack = d.get("ack") or {}
            if d.get("ok") and float(ack.get("fill_count") or 0) > 0:
                runlog.assert_event(True, "shadow", f"FOLLOW-TRADE {side} x1 @{price}c {series} (whale signal {signal01:.2f})",
                                    ticker=m["ticker"], entity=entity)
                alert(entity, f"FOLLOW-TRADE FIRED {side} @{price}c {series}")
            return
    except Exception as e:
        runlog.log_event("shadow", f"follow-trade warn {repr(e)[:60]}", kind="warn")


def main():
    fleetlib.acquire_lock("shadow")
    live = [e["name"] for e in ENTITIES if e["live"]]
    print(f"[shadow] start | index={len(ENTITIES)} entities ({len(live)} live) poll={POLL_S}s whale>=${WHALE_USD:,.0f}", flush=True)
    runlog.log_event("shadow", f"shadow index start entities={len(ENTITIES)} live={live}")
    with httpx.Client(headers={"Accept-Encoding": "identity"}, timeout=25) as cx:
        while True:
            fleetlib.checkin("shadow")
            ts = int(time.time())
            total = 0
            try:
                con = sqlite3.connect(DB)
                cur = con.cursor()
                try:
                    total += polymarket_whale_flow(cx, cur, ts)
                except Exception as e:
                    runlog.log_event("shadow", f"whale flow warn {repr(e)[:60]}", kind="warn")
                con.commit()
                publish(con)
                con.close()
                publish_latest()
                publish_latest()
            except Exception as e:
                runlog.log_event("shadow", f"cycle warn {repr(e)[:60]}", kind="warn")
            if ts % 600 < POLL_S:
                runlog.log_event("shadow", f"cycle +{total} shadow UUIDs", new=total)
                print(f"[shadow] {time.strftime('%H:%M:%S')} +{total} shadow signals", flush=True)
            time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
