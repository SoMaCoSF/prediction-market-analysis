# file_id: SOM-PY-0939-v1.0.0 name: runlog.py description: Shared zero-token run logger — structured JSONL events + inline assertions, date-rotated, readable by any agent/tool without model tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [logging, runlog, assertions, zero-token, observability] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""runlog.py — every daemon narrates itself to disk.

One JSON object per line in logs/run_YYYYMMDD.jsonl:
  {"ts": 1785700000.0, "t": "13:26:41", "actor": "scalp", "kind": "log"|"assert", "msg": "...", ...fields}

Assertions are INLINE: assert_event(cond, actor, claim, **fields) writes
kind="assert", pass=true/false, so a failed invariant is greppable forever.

Cost: file I/O only. No network, no model tokens. Readers: run_report.py,
any agent, or a human with `tail -f`.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGDIR = ROOT / "logs"
LOGDIR.mkdir(exist_ok=True)


def _path() -> Path:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return LOGDIR / f"run_{day}.jsonl"


def log_event(actor: str, msg: str, kind: str = "log", **fields):
    rec = {"ts": time.time(), "t": time.strftime("%H:%M:%S"), "actor": actor, "kind": kind, "msg": msg}
    rec.update(fields)
    try:
        with open(_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except Exception:
        pass  # logging must never crash a trading loop


def assert_event(cond: bool, actor: str, claim: str, **fields):
    log_event(actor, claim, kind="assert", **{"pass": bool(cond)}, **fields)
    return cond
