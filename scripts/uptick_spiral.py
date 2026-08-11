# file_id: SOM-PY-0998-v1.0.0 name: uptick_spiral.py description: Uptick spiral — closes the feedback loop: scores past news forecasts against actual Kalshi market resolutions, adjusts supply-chain node weights (uptick for hits, downtick for misses), publishes spiral accuracy metrics; the self-improving prediction engine project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [uptick, spiral, feedback, scoring, weights, learning, news] created: 2026-08-11 version: 1.0.0 agent_id: HERMES-AGENT
"""uptick_spiral.py — the self-improving news prediction loop.

THE PROBLEM: news_supply_engine mints forecasts (19k+) with FIXED probability
shifts that never get scored. It's an open loop — predictions go out, nothing
comes back. The system never learns which news nodes actually predict correctly.

THE SPIRAL: this daemon closes the loop.
  1. Scan the forecast stream for unscored predictions
  2. For each forecast, find the hinted Kalshi market that was open at forecast time
  3. Check if that market has resolved (settled)
  4. Score: did our predicted direction match the actual outcome?
  5. Update per-node accuracy stats (hits, misses, streak, Brier score)
  6. Adjust weights: hit nodes get upticked (bigger shift next time),
     miss nodes get downticked (smaller shift, or zero if chronic loser)
  7. Write adjusted weights to data/uptick_weights.json
  8. Publish spiral metrics to mc_state (accuracy, streak, total scored)

news_supply_engine reads data/uptick_weights.json on each cycle and uses the
adjusted shifts instead of the hardcoded ATLAS values. That's the spiral:
every cycle the weights get sharper because they're backed by real outcomes.

Scoring logic:
  - Forecast prob > 0.5 = predicted YES. Market resolved YES = HIT.
  - Forecast prob < 0.5 = predicted NO.  Market resolved NO = HIT.
  - Brier score = (prob - outcome)^2 where outcome is 1.0 or 0.0.
    Lower = better. 0.0 = perfect. 0.25 = coin flip.

Weight adjustment:
  - HIT  + uptick: shift *= 1.15 (max +0.20)
  - MISS - downtick: shift *= 0.80 (min 0.0 = node silenced)
  - 3+ miss streak: node quarantined (shift=0) until it hits again
  - Cold-start: first 5 forecasts per node use the ATLAS base shift (no adjustment)

Zero model tokens. Pure stdlib + httpx + sqlite3.
"""
from __future__ import annotations

import json
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
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

DB = ROOT / "data" / "uuid_stream.db"
WEIGHTS_FILE = ROOT / "data" / "uptick_weights.json"
SCORED_FILE = ROOT / "data" / "uptick_scored.json"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
POLL_S = 120  # 2 min — scoring doesn't need to be real-time

# Mirror the ATLAS from news_supply_engine — we need the hint (series ticker)
# and the base shift for cold-start. If news_supply_engine changes its ATLAS,
# this should be updated too (or read it dynamically — see init).
ATLAS_BASE = {
    "red-sea-shipping":    ("KXWTI", +0.08),
    "nuclear-restart":     ("KXWTI", +0.04),
    "datacenter-power":    ("KXWTI", +0.05),
    "electrical-supply":  ("KXWTI", +0.03),
    "copper-grid":        ("KXWTI", +0.04),
    "ecb-rates":          ("KXBTC15M", +0.05),
    "semis-export":       ("KXNASDAQ", +0.06),
    "energy-eu":          ("KXWTI", +0.07),
    "grain":              ("KXWHEAT", +0.06),
    "crypto-reg":         ("KXBTC15M", +0.05),
    "tariffs":            ("KXSP500", +0.05),
}

MAX_SHIFT = 0.20
MIN_SHIFT = 0.0
UPTICK_MULT = 1.15
DOWNTICK_MULT = 0.80
QUARANTINE_STREAK = 3
COLD_START_N = 5


def log(m, kind="info"):
    print(f"[{time.strftime('%H:%M:%S')}] [uptick] {m}", flush=True)
    runlog.log_event("uptick", m, kind=kind)


# ---- state ----

def load_weights() -> dict:
    """Load adjusted weights, or init from ATLAS_BASE on first run."""
    if WEIGHTS_FILE.exists():
        try:
            return json.loads(WEIGHTS_FILE.read_text())
        except Exception:
            pass
    # init from base
    w = {}
    for node, (hint, base_shift) in ATLAS_BASE.items():
        w[node] = {
            "hint": hint,
            "shift": base_shift,
            "base_shift": base_shift,
            "hits": 0,
            "misses": 0,
            "streak": 0,  # positive = hit streak, negative = miss streak
            "brier_sum": 0.0,
            "scored": 0,
            "quarantined": False,
        }
    save_weights(w)
    log(f"initialized weights for {len(w)} nodes from ATLAS_BASE")
    return w


def save_weights(w: dict):
    WEIGHTS_FILE.write_text(json.dumps(w, indent=2))


def load_scored() -> set[str]:
    """Set of already-scored forecast UUIDs (don't re-score)."""
    if SCORED_FILE.exists():
        try:
            return set(json.loads(SCORED_FILE.read_text()))
        except Exception:
            pass
    return set()


def save_scored(scored: set[str]):
    # keep only last 5000 to avoid unbounded growth
    recent = list(scored)[-5000:]
    SCORED_FILE.write_text(json.dumps(recent))


# ---- market resolution ----

def get_market_outcome(cx, series_ticker, forecast_ts):
    """Find the Kalshi market in this series that was open at forecast_ts and
    check if it has settled. Returns (resolved: bool, yes_won: bool|None).

    Uses status=settled which returns markets with status='finalized' and
    a 'result' field of 'yes' or 'no'.
    """
    try:
        r = cx.get(f"{KALSHI}/markets",
                    params={"limit": 100, "status": "settled", "series_ticker": series_ticker},
                    timeout=20)
        markets = r.json().get("markets", [])
        for m in markets:
            close_str = m.get("close_time", "")
            if not close_str:
                continue
            from datetime import datetime
            close_dt = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
            close_ts = close_dt.timestamp()
            # Was this market open at forecast time?
            # Market must have closed AFTER the forecast (forecast was about this window)
            window_s = close_ts - forecast_ts
            if window_s < 0:
                continue  # market already closed before forecast — skip
            # Only score markets that closed at least 60s ago (definitely settled)
            if close_ts > time.time() - 60:
                continue  # not settled yet
            # Read the result field: 'yes' or 'no'
            result = (m.get("result") or "").strip().lower()
            if result == "yes":
                return True, True
            if result == "no":
                return True, False
            # Fallback: check bid/ask for settled YES (bid=1.00) or NO (bid=0.00)
            yb = float(m.get("yes_bid_dollars") or 0)
            if yb >= 0.95:
                return True, True
            if yb <= 0.05:
                return True, False
            # Can't determine outcome — skip
        return False, None
    except Exception as e:
        log(f"market outcome warn for {series_ticker}: {repr(e)[:80]}", kind="warn")
        return False, None


def get_unscored_forecasts(scored: set[str]) -> list[dict]:
    """Get forecasts from the stream DB that haven't been scored yet."""
    con = sqlite3.connect(DB)
    cur = con.cursor()
    # We stored forecasts as source='forecast', symbol=node_name, price_c=prob*100
    cur.execute("""
        SELECT uuid, ts, symbol, price_c FROM stream
        WHERE source='forecast' ORDER BY ts DESC LIMIT 200
    """)
    rows = cur.fetchall()
    con.close()
    import re
    unscored = []
    for uuid, ts, node, detail in rows:
        if uuid in scored:
            continue
        # The probability is embedded in the detail string as p=0.XX
        # (news_supply_engine stores detail text in price_c, not a numeric prob)
        prob = 0.5  # fallback
        if detail and isinstance(detail, str):
            m = re.search(r'p=([0-9.]+)', detail)
            if m:
                try:
                    prob = float(m.group(1))
                except ValueError:
                    pass
        unscored.append({"uuid": uuid, "ts": ts, "node": node, "prob": prob})
    return unscored


# ---- scoring + weight adjustment ----

def score_forecast(cx, fc, weights):
    """Score a single forecast. Returns (scored: bool, hit: bool|None, brier: float|None)."""
    node = fc["node"]
    if node not in weights:
        # Unknown node — not in our ATLAS. Skip.
        return False, None, None

    w = weights[node]
    hint = w["hint"]
    prob = fc["prob"]

    resolved, yes_won = get_market_outcome(cx, hint, fc["ts"])
    if not resolved or yes_won is None:
        return False, None, None  # market not settled yet or can't determine

    # Score: did our predicted direction match?
    predicted_yes = prob >= 0.5
    hit = (predicted_yes == yes_won)

    # Brier score: (prob - outcome)^2
    outcome = 1.0 if yes_won else 0.0
    brier = (prob - outcome) ** 2

    # Update node stats
    w["scored"] += 1
    w["brier_sum"] += brier
    if hit:
        w["hits"] += 1
        w["streak"] = max(1, w["streak"] + 1) if w["streak"] >= 0 else 1
        # UPTICK: boost the shift
        if w["scored"] > COLD_START_N:
            w["shift"] = min(MAX_SHIFT, w["shift"] * UPTICK_MULT)
        # Un-quarantine if it was quarantined and just hit
        if w["quarantined"]:
            w["quarantined"] = False
            w["shift"] = w["base_shift"]  # reset to base, earn trust back
            log(f"node {node} UNQUARANTINED — hit after quarantine")
    else:
        w["misses"] += 1
        w["streak"] = min(-1, w["streak"] - 1) if w["streak"] <= 0 else -1
        # DOWNTICK: shrink the shift
        if w["scored"] > COLD_START_N:
            w["shift"] = max(MIN_SHIFT, w["shift"] * DOWNTICK_MULT)
        # QUARANTINE: chronic losers get silenced
        if w["streak"] <= -QUARANTINE_STREAK:
            if not w["quarantined"]:
                w["quarantined"] = True
                w["shift"] = 0.0
                log(f"node {node} QUARANTINED — {abs(w['streak'])} misses in a row", kind="warn")

    return True, hit, brier


def publish_spiral(weights):
    """Publish spiral metrics to mc_state for the panel."""
    try:
        total_scored = sum(w["scored"] for w in weights.values())
        total_hits = sum(w["hits"] for w in weights.values())
        total_brier = sum(w["brier_sum"] for w in weights.values())
        accuracy = total_hits / total_scored if total_scored else 0.0
        mean_brier = total_brier / total_scored if total_scored else 0.25

        # Top performing nodes (by accuracy, min 5 scored)
        ranked = sorted(
            [(n, w) for n, w in weights.items() if w["scored"] >= 5],
            key=lambda x: x[1]["hits"] / max(1, x[1]["scored"]),
            reverse=True
        )
        panel = {
            "total_scored": total_scored,
            "total_hits": total_hits,
            "accuracy": round(accuracy, 4),
            "mean_brier": round(mean_brier, 4),
            "active_nodes": sum(1 for w in weights.values() if not w["quarantined"]),
            "quarantined_nodes": sum(1 for w in weights.values() if w["quarantined"]),
            "top_nodes": [
                {"node": n, "hits": w["hits"], "scored": w["scored"],
                 "accuracy": round(w["hits"] / w["scored"], 3),
                 "streak": w["streak"], "shift": round(w["shift"], 4),
                 "brier": round(w["brier_sum"] / w["scored"], 4) if w["scored"] else 0.25}
                for n, w in ranked[:10]
            ],
            "all_nodes": {
                n: {"shift": round(w["shift"], 4), "hits": w["hits"], "misses": w["misses"],
                    "streak": w["streak"], "scored": w["scored"],
                    "accuracy": round(w["hits"] / w["scored"], 3) if w["scored"] else 0,
                    "quarantined": w["quarantined"]}
                for n, w in weights.items()
            },
        }
        con = sb.sb_conn()
        con.autocommit = True
        con.cursor().execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('uptick:spiral', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (json.dumps(panel),))
        con.close()
        return panel
    except Exception as e:
        log(f"publish warn {repr(e)[:80]}", kind="warn")
        return None


# ---- main loop ----

def main():
    fleetlib.acquire_lock("uptick")
    log("uptick spiral start — closing the feedback loop")
    weights = load_weights()
    scored = load_scored()
    log(f"loaded {len(weights)} node weights, {len(scored)} already-scored UUIDs")

    with httpx.Client(timeout=30) as cx:
        while True:
            fleetlib.checkin("uptick")
            try:
                unscored = get_unscored_forecasts(scored)
                if not unscored:
                    time.sleep(POLL_S)
                    continue

                newly_scored = 0
                newly_hit = 0
                for fc in unscored:
                    did_score, hit, brier = score_forecast(cx, fc, weights)
                    if did_score:
                        scored.add(fc["uuid"])
                        newly_scored += 1
                        if hit:
                            newly_hit += 1
                        if newly_scored % 10 == 0:
                            save_weights(weights)
                            save_scored(scored)

                if newly_scored:
                    save_weights(weights)
                    save_scored(scored)
                    acc = newly_hit / newly_scored if newly_scored else 0
                    log(f"scored {newly_scored} forecasts ({newly_hit} hits, {acc:.1%} accuracy)")

                panel = publish_spiral(weights)
                if panel and newly_scored:
                    log(f"spiral: {panel['total_scored']} total scored, "
                        f"{panel['accuracy']:.1%} accuracy, "
                        f"{panel['active_nodes']} active, "
                        f"{panel['quarantined_nodes']} quarantined, "
                        f"brier={panel['mean_brier']:.3f}")

            except Exception as e:
                log(f"cycle warn {repr(e)[:80]}", kind="warn")
            time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
