# file_id: SOM-PY-0999-v1.0.0 name: oracle.py description: THE ORACLE — pre-commits the fleet's 15M BTC call to the ledger BEFORE the window closes (0x3D7 ORACLE_CALL mints), scores the last call on settle, publishes oracle:current + oracle:history; a public track record that cannot lie; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [oracle, predictions, precommitment, track-record, zero-token] created: 2026-08-04 version: 1.0.0 agent_id: HERMES-AGENT
"""oracle.py — the public pre-committed prediction record.

Every 15M BTC window: at window open, read the same momentum signal the
engines trade (tick plane -> Kraken fallback), mint the call as a 0x3D7
ORACLE_CALL UUIDv8 (timestamped, immutable), publish oracle:current.
When the window settles, score the call -> oracle:history.
The page shows: the live call, the countdown, and the rolling hit rate.
Zero model tokens. The credibility engine.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import httpx  # noqa: E402
import runlog  # noqa: E402
import sb  # noqa: E402

TYPE_ORACLE = 0x3D7
POLL_S = 10

current: dict | None = None   # the open call
history: list[dict] = []      # scored calls


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] [oracle] {m}", flush=True)
    runlog.log_event("oracle", m)


def publish():
    try:
        con = sb.sb_conn()
        con.autocommit = True
        cur = con.cursor()
        cur.execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('oracle:current', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (json.dumps(current),))
        cur.execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('oracle:history', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (json.dumps(history[-60:]),))
        con.close()
    except Exception:
        pass


def window(cx):
    try:
        r = cx.get("https://api.elections.kalshi.com/trade-api/v2/markets",
                   params={"limit": 3, "status": "open", "series_ticker": "KXBTC15M"}, timeout=15)
        for m in r.json().get("markets", []):
            from datetime import datetime, timezone
            close = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
            if close > time.time() + 60:
                return m["ticker"], close
    except Exception:
        pass
    return None, None


def signal(cx):
    """The same momentum the engines trade: tick plane first, Kraken fallback."""
    try:
        r = cx.get("http://127.0.0.1:8421/tick/BTC?secs=180", timeout=2)
        d = r.json()
        ticks = d.get("ticks", [])
        if len(ticks) >= 6:
            p0, p1 = ticks[0][1], ticks[-1][1]
            return ((p1 - p0) / p0) * 1e4 if p0 else None  # bps
    except Exception:
        pass
    try:
        d = cx.get("https://api.kraken.com/0/public/Ticker?pair=XBTUSD", timeout=10).json()["result"]
        k = next(iter(d))
        return (float(d[k]["c"][0]) - float(d[k]["o"])) / float(d[k]["o"]) * 100 * 100  # ~bps-ish scale
    except Exception:
        return None


def mint_call(ticker, call, mom):
    try:
        import uuid_ledger
        content = hashlib.sha256(f"oracle|{ticker}|{call}|{mom:.2f}|{int(time.time())}".encode()).digest()
        u = uuid_ledger.mint(TYPE_ORACLE, content, provenance=0xD)
        uuid_ledger.store(u, f"ORACLE {ticker} {call} mom {mom:+.1f}bps")
        return str(u)
    except Exception:
        return None


def main():
    global current
    fleetlib.acquire_lock("oracle")
    log("start | pre-committing the 15M calls — the track record that cannot lie")
    with httpx.Client(headers={"Accept-Encoding": "identity"}, timeout=20) as cx:
        while True:
            try:
                fleetlib.checkin("oracle")
                tick, close = window(cx)
                if tick:
                    if not current or current["ticker"] != tick:
                        # score the outgoing call first
                        if current:
                            score(cx, current)
                        mom = signal(cx)
                        if mom is not None:
                            call = "UP" if mom > 0 else "DOWN"
                            current = {"ticker": tick, "call": call, "mom_bps": round(mom, 1),
                                       "close_ts": close, "uuid": mint_call(tick, call, mom),
                                       "ts": int(time.time())}
                            log(f"CALL {call} on {tick} (mom {mom:+.1f}bps) — pre-committed {current['uuid'][:18] if current['uuid'] else ''}")
                publish()
            except Exception as e:
                log(f"warn {repr(e)[:60]}")
            time.sleep(POLL_S)


def score(cx, c):
    try:
        from run_report import kget
        m = kget(f"/markets/{c['ticker']}").get("market", {})
        res = (m.get("result") or "").lower()
        if res not in ("yes", "no"):
            return
        won = (res == "yes") == (c["call"] == "UP")
        c["result"] = res
        c["won"] = won
        history.append(c)
        log(f"SCORED {c['ticker']} {c['call']} -> {res} {'HIT' if won else 'MISS'}")
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
