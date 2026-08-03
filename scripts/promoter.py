# file_id: SOM-PY-0986-v1.0.0 name: promoter.py description: Dry-winner promoter — every 30min scans 24h of runlog dry-lane events, computes per-variant win rate + realized, crowns the highest-expectancy lane (n>=10), writes data/engine_params.json for the live trend engines to adopt project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [promoter, dry-run, expectancy, params, zero-token] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""promoter.py — the dry lanes vote; the live engines take the winner's params.

Every 30 min:
  1. Read the last 24h of logs/run_*.jsonl events for the dry lanes
     (actor='dry' + lane field; dry_run.py tags every report with lane=LANE).
     Events are CUMULATIVE within one dry run (hourly process), so per lane
     the stream is split into run-segments wherever the counters reset, and
     each segment's last event contributes its totals.
  2. Per variant: n = wins+losses, win_rate, realized_usd,
     expectancy = realized / n.
  3. Winner = highest expectancy with n >= MIN_N (tie-break: realized, n).
  4. Atomic-write data/engine_params.json:
     {"take": X, "stop": Y, "source": lane, "n": N, "ts": ...}
     Live trend_engine lanes adopt it (startup + every 50 cycles).

Param mapping: dry t-lanes run scalp-only (dry engine has no stop path),
so their stop maps to the live default 10; dry-s15-8 maps to its 8.
Transitional fallback: lanes with no lane-tagged runlog events yet get their
current-run stats from the last report line of logs/<lane>.out.log, so the
standings are real from minute 0. Zero network, zero model tokens.

Usage: promoter.py        # daemon loop (supervisor-managed)
       promoter.py once   # single cycle, print standings, exit
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import runlog  # noqa: E402

LOGDIR = ROOT / "logs"
PARAMS = ROOT / "data" / "engine_params.json"
WINDOW_S = 24 * 3600
CYCLE_S = 30 * 60
MIN_N = 10

# lane -> (TAKE, STOP) as live-engine params. Dry t-lanes run stop=0 (the dry
# engine has no stop-loss path at all), so they map to the proven live stop 10.
LANES: dict[str, tuple[int, int]] = {
    "dry-t10": (10, 10),
    "dry-t20": (20, 10),
    "dry-t25": (25, 10),
    "dry-s15-8": (15, 8),
}

REPORT_RE = re.compile(r"W/L=(\d+)/(\d+) realized=\$([+-]?[\d.]+)")


def _runlog_paths(now: float) -> list[Path]:
    """run_YYYYMMDD.jsonl files that can hold events inside the window."""
    out = []
    for p in sorted(LOGDIR.glob("run_*.jsonl")):
        try:
            if p.stat().st_mtime >= now - WINDOW_S - 3600:
                out.append(p)
        except Exception:
            pass
    return out


def _events_from_runlog(now: float) -> dict[str, list[dict]]:
    """Lane-tagged dry report events inside the window, per lane, ts-sorted."""
    per_lane: dict[str, list[dict]] = {k: [] for k in LANES}
    for path in _runlog_paths(now):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if rec.get("ts", 0) < now - WINDOW_S:
                        continue
                    if not isinstance(rec.get("wins"), int) or not isinstance(rec.get("losses"), int):
                        continue
                    lane = rec.get("lane")
                    if lane not in LANES and rec.get("actor") in LANES:
                        lane = rec["actor"]  # future-proof: actor-as-lane
                    if lane in LANES and (rec.get("actor") == "dry" or rec.get("actor") in LANES):
                        per_lane[lane].append(rec)
        except Exception:
            pass
    for evs in per_lane.values():
        evs.sort(key=lambda r: r.get("ts", 0))
    return per_lane


def _sum_segments(evs: list[dict]) -> tuple[int, int, float]:
    """Sum per-run totals from cumulative events.

    Events are cumulative within one dry-run process. A run segment closes
    when (a) a FINAL-tagged event arrives (it holds the full run total, so it
    supersedes the open segment), or (b) counters reset (n drops -> new run),
    which credits the previous segment's last event.
    """
    wins = losses = 0
    realized = 0.0
    seg_last: dict | None = None

    def credit(rec: dict) -> None:
        nonlocal wins, losses, realized
        wins += rec["wins"]
        losses += rec["losses"]
        realized += float(rec.get("realized_usd") or 0.0)

    for rec in evs:
        n = rec["wins"] + rec["losses"]
        if rec.get("tag") == "FINAL":
            credit(rec)          # FINAL is the run total — supersedes segment
            seg_last = None
        elif seg_last is not None and n < seg_last["wins"] + seg_last["losses"]:
            credit(seg_last)     # counter reset -> previous run ended here
            seg_last = rec
        else:
            seg_last = rec
    if seg_last is not None:
        credit(seg_last)
    return wins, losses, realized


def _fallback_outlog(lane: str, now: float) -> tuple[int, int, float]:
    """Transitional: last report line of logs/<lane>.out.log (current run only)."""
    p = LOGDIR / f"{lane}.out.log"
    try:
        if not p.exists() or p.stat().st_mtime < now - WINDOW_S:
            return 0, 0, 0.0
        for line in reversed(p.read_text(encoding="utf-8", errors="ignore").splitlines()[-200:]):
            m = REPORT_RE.search(line)
            if m:
                return int(m.group(1)), int(m.group(2)), float(m.group(3))
    except Exception:
        pass
    return 0, 0, 0.0


def standings(now: float) -> dict[str, dict]:
    per_lane = _events_from_runlog(now)
    out: dict[str, dict] = {}
    for lane, (take, stop) in LANES.items():
        evs = per_lane[lane]
        if evs:
            wins, losses, realized = _sum_segments(evs)
            src = "runlog"
        else:
            wins, losses, realized = _fallback_outlog(lane, now)
            src = "outlog"
        n = wins + losses
        out[lane] = {
            "take": take, "stop": stop, "wins": wins, "losses": losses, "n": n,
            "win_rate": round(wins / n, 4) if n else 0.0,
            "realized_usd": round(realized, 4),
            "expectancy_usd": round(realized / n, 4) if n else 0.0,
            "src": src,
        }
    return out


def pick_winner(board: dict[str, dict]) -> tuple[str, dict] | tuple[None, None]:
    qualified = {k: v for k, v in board.items() if v["n"] >= MIN_N}
    if not qualified:
        return None, None
    lane = max(qualified, key=lambda k: (qualified[k]["expectancy_usd"],
                                         qualified[k]["realized_usd"], qualified[k]["n"]))
    return lane, qualified[lane]


def write_params(lane: str, stats: dict) -> dict:
    rec = {
        "take": stats["take"], "stop": stats["stop"], "source": lane,
        "n": stats["n"], "ts": time.time(),
        "win_rate": stats["win_rate"], "expectancy_usd": stats["expectancy_usd"],
        "realized_usd": stats["realized_usd"],
    }
    tmp = PARAMS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    os.replace(tmp, PARAMS)  # atomic on same volume
    return rec


def cycle() -> None:
    now = time.time()
    board = standings(now)
    summary = " | ".join(
        f"{k} n={v['n']} W/L={v['wins']}/{v['losses']} exp=${v['expectancy_usd']:+.3f} "
        f"real=${v['realized_usd']:+.2f} ({v['src']})" for k, v in board.items())
    print(f"[promoter] {summary}", flush=True)
    runlog.log_event("promoter", f"standings {summary}")
    lane, stats = pick_winner(board)
    if lane is None:
        print(f"[promoter] no qualifier (n>={MIN_N}) — params unchanged", flush=True)
        runlog.log_event("promoter", f"no qualifier n>={MIN_N} — params unchanged")
        return
    rec = write_params(lane, stats)
    print(f"[promoter] PROMOTED {lane}: take={rec['take']} stop={rec['stop']} "
          f"n={rec['n']} exp=${stats['expectancy_usd']:+.3f}/trade", flush=True)
    runlog.assert_event(True, "promoter", f"promoted {lane}", **rec)


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        cycle()
        return 0
    fleetlib.acquire_lock("promoter")
    runlog.log_event("promoter", "promoter start", lanes=list(LANES), min_n=MIN_N)
    print(f"[promoter] start: lanes={list(LANES)} cycle={CYCLE_S}s min_n={MIN_N}", flush=True)
    last = 0.0
    while True:
        fleetlib.checkin("promoter")
        if time.time() - last >= CYCLE_S:
            try:
                cycle()
            except Exception as e:
                runlog.log_event("promoter", f"cycle warn {repr(e)[:80]}", kind="warn")
                print(f"[promoter] cycle warn {repr(e)[:80]}", flush=True)
            last = time.time()
        time.sleep(30)  # checkin cadence << 180s supervisor HUNG threshold


if __name__ == "__main__":
    sys.exit(main())
