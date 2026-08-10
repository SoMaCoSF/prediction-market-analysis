# file_id: SOM-PY-0945-v1.0.0 name: dry_run.py description: Massive parallel paper engine — all 5 crypto 15M series, up to 3 open per series, simulated taker fills from real books, scalp+settle exits, hypothetical P&L report; zero real money, zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [dry-run, paper, parallel, simulation, momentum] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""dry_run.py — where would we be? Paper-parallel the momentum strategy.

Every 5s, for each series (BTC/ETH/SOL/XRP/DOGE 15M):
  ENTER: early window (ttl>=540s), drift>=±0.20%, ask<=60c, <3 open per series
         -> paper buy at the ASK (taker realism).
  EXIT : bid >= entry+15c -> paper sell (scalp path); else settle at result.
Fees ~1.75c taker per contract at 50c (0.07*C*P*(1-P) exact).
Report every window + final: entries, exits, win rate, gross, fees, net,
max drawdown of paper equity. Logs to runlog as actor 'dry'. NO real orders.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import httpx  # noqa: E402
import runlog  # noqa: E402
import sb  # noqa: E402

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = [
    ("KXBTC15M", "XBTUSD"),
    ("KXETH15M", "ETHUSD"),
    ("KXSOL15M", "SOLUSD"),
    ("KXXRP15M", "XRPUSD"),
    ("KXDOGE15M", "DOGEUSD"),
]
# Non-crypto markets the fleet actually trades live (verified open on Kalshi).
# pair=None -> drift() uses the Kalshi market's own previous-print move.
SERIES_NONCRYPTO = [
    ("KXWTI", None),       # WTI oil 15-min windows (energy)
    ("KXNGASMIN", None),   # Natural gas yearly min
]
DRIFT_MIN, ENTRY_MAX, TTL_MIN = 0.20, 60, 540
SCALP_C = int(sys.argv[2]) if len(sys.argv) > 2 else 15
STOP_C = int(sys.argv[3]) if len(sys.argv) > 3 else 0
LANE = sys.argv[4] if len(sys.argv) > 4 else "dry"
MAX_OPEN_PER_SERIES = 3
POLL = 5
RUN_MINUTES = int(sys.argv[1]) if len(sys.argv) > 1 else 60
# CLIP_CENTS (argv[5]): the $ size we'd actually trade per entry (sweet-spot check).
# The live fleet now trades $1-$3 clips; the sim must model that fee, not 1 contract.
CLIP_CENTS = int(sys.argv[5]) if len(sys.argv) > 5 else 100  # default $1.00
START_EQUITY = 25.00

positions: list[dict] = []  # {ticker, series, side, entry_c, ts, window_close}
realized = 0.0
fees = 0.0
entries = scalp_exits = settles = wins = losses = 0
equity_peak = START_EQUITY
max_dd = 0.0


def fee_c(price_c: float, count: int = 1) -> float:
    p = price_c / 100.0
    return 0.07 * count * p * (1 - p) * 100  # cents


# Real clip sizing: a $CLIP_CENTS entry at price_c costs (CLIP_CENTS/price_c) contracts.
def clip_count(price_c: float) -> int:
    pc = max(1, price_c)
    return max(1, round(CLIP_CENTS / pc))


def drift(cx, pair, series=None):
    if pair:
        try:
            d = cx.get(f"https://api.kraken.com/0/public/Ticker?pair={pair}", timeout=10).json()["result"]
            k = next(iter(d))
            return (float(d[k]["c"][0]) - float(d[k]["o"])) / float(d[k]["o"]) * 100
        except Exception:
            pass
    # Non-crypto / pairless -> Kalshi market's own recent move (previous print vs current)
    if series:
        try:
            r = cx.get(f"{KALSHI}/markets", params={"limit": 1, "status": "open", "series_ticker": series}, timeout=15).json()
            m = (r.get("markets") or [{}])[0]
            prev = float(m.get("previous_yes_bid_dollars") or m.get("previous_price_dollars") or 0)
            cur = float(m.get("yes_bid_dollars") or m.get("last_price_dollars") or 0)
            if prev > 0:
                return (cur - prev) / prev * 100
        except Exception:
            pass
    return 0.0


def window_market(cx, series):
    r = cx.get(f"{KALSHI}/markets", params={"limit": 5, "status": "open", "series_ticker": series}, timeout=15)
    for m in r.json().get("markets", []):
        ya = float(m.get("yes_ask_dollars") or 0)
        if not (0 < ya < 1):
            continue
        close = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
        ttl = close - time.time()
        if ttl >= TTL_MIN:
            return {
                "ticker": m["ticker"],
                "ya": round(ya * 100),
                "yb": round(float(m.get("yes_bid_dollars") or 0) * 100),
                "ttl": ttl,
                "close": close,
            }
    return None


def book(cx, ticker):
    m = cx.get(f"{KALSHI}/markets/{ticker}", timeout=15).json().get("market", {})
    return {
        "ya": float(m.get("yes_ask_dollars") or 0) * 100,
        "yb": float(m.get("yes_bid_dollars") or 0) * 100,
        "result": (m.get("result") or "").lower(),
    }


def equity(open_marks: float) -> float:
    return START_EQUITY + realized - fees + open_marks


def publish(open_marks: float, last_event: str = ""):
    """Publish dry-run state to Supabase for dry.somacosf.com (never crash the sim)."""
    try:
        import json as _json

        con = sb.sb_conn()
        con.autocommit = True
        cur = con.cursor()
        state = {
            "lane": LANE,
            "clip_usd": round(CLIP_CENTS / 100, 2),
            "entries": entries,
            "scalps": scalp_exits,
            "settles": settles,
            "wins": wins,
            "losses": losses,
            "realized": round(realized, 4),
            "fees": round(fees, 4),
            "equity": round(equity(open_marks), 4),
            "max_dd": round(max_dd, 4),
            "start_equity": START_EQUITY,
            "net": round(realized - fees, 4),
            "open": [{"ticker": p["ticker"], "side": p["side"], "entry_c": p["entry_c"]} for p in positions],
            "run_minutes": RUN_MINUTES,
            "ts": time.time(),
        }
        # Per-lane key so parallel runs ($1 vs $3 clip) don't clobber each other.
        cur.execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES (%s, %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (f"dry_run_state:{LANE}", _json.dumps(state)),
        )
        if last_event:
            cur.execute("INSERT INTO mc_log (ts, kind, msg) VALUES (%s, 'dry', %s)", (int(time.time()), last_event))
        con.close()
    except Exception:
        pass


def report(cx, tag):
    open_marks = 0.0
    for p in positions:
        try:
            b = book(cx, p["ticker"])
            px = b["yb"] if p["side"] == "yes" else (100 - b["ya"])
            open_marks += (px - p["entry_c"]) / 100.0
        except Exception:
            pass
    eq = equity(open_marks)
    msg = (
        f"[{tag}] entries={entries} scalps={scalp_exits} settles={settles} "
        f"W/L={wins}/{losses} realized=${realized:+.2f} fees=${fees:.2f} "
        f"open={len(positions)} mark=${open_marks:+.2f} equity=${eq:.2f} maxDD=${max_dd:.2f}"
    )
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
    runlog.log_event(
        "dry",
        msg,
        tag=tag,
        entries=entries,
        wins=wins,
        losses=losses,
        realized_usd=round(realized, 4),
        equity_usd=round(eq, 4),
        lane=LANE,
        take_c=SCALP_C,
        stop_c=STOP_C,
    )
    publish(open_marks, msg)


def main():
    global realized, fees, entries, scalp_exits, settles, wins, losses, equity_peak, max_dd
    fleetlib.acquire_lock(LANE)
    # argv[6]: "noncrypto" selects equities/commodities series; else crypto 15M
    mode = sys.argv[6] if len(sys.argv) > 6 else "crypto"
    SERIES_USED = SERIES_NONCRYPTO if mode == "noncrypto" else SERIES
    end = time.time() + RUN_MINUTES * 60
    print(
        f"[dry] start: {len(SERIES_USED)} series ({mode}) x{MAX_OPEN_PER_SERIES} open, {RUN_MINUTES}min, paper ${START_EQUITY}",
        flush=True,
    )
    runlog.log_event("dry", f"dry run start {RUN_MINUTES}min", minutes=RUN_MINUTES, lane=LANE)
    with httpx.Client(headers={"Accept-Encoding": "identity"}) as cx:
        last_report = 0
        while time.time() < end:
            fleetlib.checkin("dry")
            # --- exits ---
            for p in list(positions):
                try:
                    b = book(cx, p["ticker"])
                except Exception:
                    continue
                now = time.time()
                if b["result"] in ("yes", "no"):
                    won = b["result"] == p["side"]
                    pnl = (100 - p["entry_c"]) if won else (-p["entry_c"])
                    realized += (pnl / 100.0) * clip_count(p["entry_c"])
                    fees += fee_c(p["entry_c"], clip_count(p["entry_c"])) / 100.0
                    settles += 1
                    wins += 1 if won else 0
                    losses += 0 if won else 1
                    print(
                        f"[{time.strftime('%H:%M:%S')}] SETTLE {p['ticker'][:34]} {p['side']}@{p['entry_c']}c -> {b['result']} {'WIN' if won else 'LOSS'} {pnl:+}c",
                        flush=True,
                    )
                    publish(
                        0.0,
                        f"SETTLE {p['ticker'][:34]} {p['side']}@{p['entry_c']}c -> {b['result']} {'WIN' if won else 'LOSS'} {pnl:+}c",
                    )
                    positions.remove(p)
                elif p["side"] == "yes" and b["yb"] >= p["entry_c"] + SCALP_C:
                    pnl = b["yb"] - p["entry_c"]
                    realized += (pnl / 100.0) * clip_count(b["yb"])
                    fees += fee_c(b["yb"], clip_count(b["yb"])) / 100.0
                    scalp_exits += 1
                    wins += 1
                    print(
                        f"[{time.strftime('%H:%M:%S')}] SCALP-OUT {p['ticker'][:34]} @{b['yb']:.0f}c (in {p['entry_c']}c) +{pnl:.0f}c",
                        flush=True,
                    )
                    positions.remove(p)
                elif p["side"] == "no" and (100 - b["ya"]) >= p["entry_c"] + SCALP_C:
                    px = 100 - b["ya"]
                    pnl = px - p["entry_c"]
                    realized += (pnl / 100.0) * clip_count(px)
                    fees += fee_c(px, clip_count(px)) / 100.0
                    scalp_exits += 1
                    wins += 1
                    print(
                        f"[{time.strftime('%H:%M:%S')}] SCALP-OUT {p['ticker'][:34]} NO @{px:.0f}c (in {p['entry_c']}c) +{pnl:.0f}c",
                        flush=True,
                    )
                    positions.remove(p)
                elif now > p["close"] + 30:
                    positions.remove(p)  # window gone w/o result; drop mark
            # --- entries ---
            for series, pair in SERIES_USED:
                open_n = sum(1 for p in positions if p["series"] == series)
                if open_n >= MAX_OPEN_PER_SERIES:
                    continue
                try:
                    m = window_market(cx, series)
                    if not m or any(p["ticker"] == m["ticker"] for p in positions):
                        continue
                    d = drift(cx, pair, series)
                    if d >= DRIFT_MIN and m["ya"] <= ENTRY_MAX:
                        side, price = "yes", m["ya"]
                    elif d <= -DRIFT_MIN and (100 - m["yb"]) <= ENTRY_MAX:
                        side, price = "no", 100 - m["yb"]
                    else:
                        continue
                    positions.append(
                        {
                            "ticker": m["ticker"],
                            "series": series,
                            "side": side,
                            "entry_c": price,
                            "ts": time.time(),
                            "close": m["close"],
                        }
                    )
                    entries += 1
                    print(
                        f"[{time.strftime('%H:%M:%S')}] PAPER-ENTRY {side.upper()} @ {price}c {series} drift {d:+.2f}% ttl {m['ttl']:.0f}s",
                        flush=True,
                    )
                    publish(0.0, f"ENTRY {side.upper()} @ {price}c {series} drift {d:+.2f}%")
                except Exception:
                    pass
            eq = equity(0.0)
            equity_peak = max(equity_peak, eq)
            max_dd = max(max_dd, equity_peak - eq)
            if time.time() - last_report > 300:
                report(cx, "5min")
                last_report = time.time()
            time.sleep(POLL)
        report(cx, "FINAL")
        print("[dry] done", flush=True)
        runlog.log_event("dry", "dry run complete", minutes=RUN_MINUTES, lane=LANE)


if __name__ == "__main__":
    sys.exit(main())
