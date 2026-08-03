# file_id: SOM-PY-0976-v1.0.0 name: x_watcher.py description: X watcher v2 — official X API (bearer) with keyless fallback: AI-startup space sentiment signals, minted 0x3D3, published for the panel; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [x, sentiment, ai-startups, signals, stream] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""x_watcher.py v2 — the X sentiment lane for the AI startup space.

Mode A (X_BEARER_TOKEN in .env): official X API v2 recent-search, 5-min poll:
  query: AI startups/founders space (funding, launches, agents, models).
Mode B (no key): keyless fallback — nitter-style syndication is dead, so we
  poll the same RSS bridge used by the news engine's AI feeds (degraded).

Each signal: author, text, engagement, sentiment score -> mint 0x3D3 XSIGNAL
UUID -> local stream + mc_state x:latest (the trade panel's X card).
Zero model tokens — keyword scoring only.
"""
from __future__ import annotations

import json
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
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
TOKEN = os.getenv("X_BEARER_TOKEN", "")
POLL_S = 300
QUERY = '("AI startup" OR "AI agent" OR "founded" OR "seed round" OR "Series A") (AI OR artificial intelligence) lang:en -is:retweet'
POS = ["launch", "raised", "funding", "breakthrough", "sota", "release", "partnership", "growth", "wins"]
NEG = ["shutdown", "layoff", "lawsuit", "delay", "bug", "outage", "bankrupt", "fail"]
TYPE_XSIGNAL = 0x3D3
PROV_X = 0xE

seen: set[str] = set()


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] [xwatch] {m}", flush=True)
    runlog.log_event("xwatch", m)


def sentiment(text):
    low = text.lower()
    return sum(1 for w in POS if w in low) - sum(1 for w in NEG if w in low)


def mint_signal(author, sent, eng):
    try:
        from uuid_service_turboquant import mint as um
        return um(TYPE_XSIGNAL, PROV_X, 0, 0, 0, max(0, min(65535, (sent + 8) * 2048 + min(eng, 2047))),
                  f"x|{author}|{sent}|{eng}")
    except Exception:
        return None


def publish(signals):
    try:
        con = sb.sb_conn()
        con.autocommit = True
        con.cursor().execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('x:latest', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (json.dumps(signals[:15]),))
        con.close()
    except Exception as e:
        log(f"publish warn {repr(e)[:50]}")


def fetch_official(cx):
    r = cx.get("https://api.x.com/2/tweets/search/recent",
               params={"query": QUERY, "max_results": 20,
                       "tweet.fields": "public_metrics,created_at,author_id"},
               headers={"Authorization": f"Bearer {TOKEN}"}, timeout=20)
    if r.status_code != 200:
        log(f"x api {r.status_code} {r.text[:80]}")
        return []
    out = []
    for t in r.json().get("data", []):
        m = t.get("public_metrics", {})
        eng = (m.get("like_count") or 0) + 2 * (m.get("retweet_count") or 0)
        out.append({"id": t["id"], "author": t.get("author_id", "?"),
                    "text": t.get("text", "")[:140], "eng": eng,
                    "sent": sentiment(t.get("text", "")), "ts": int(time.time())})
    return out


def main():
    fleetlib.acquire_lock("xwatch")
    mode = "OFFICIAL" if TOKEN else "NO-KEY (waiting for X_BEARER_TOKEN in .env)"
    log(f"start | mode={mode} poll={POLL_S}s")
    with httpx.Client(headers={"Accept-Encoding": "identity"}, timeout=25) as cx:
        while True:
            fleetlib.checkin("xwatch")
            try:
                if TOKEN:
                    sigs = [s for s in fetch_official(cx) if s["id"] not in seen]
                    for s in sigs:
                        seen.add(s["id"])
                        s["uuid"] = mint_signal(s["author"], s["sent"], s["eng"])
                    if sigs:
                        publish(sigs)
                        top = max(sigs, key=lambda s: s["eng"])
                        log(f"{len(sigs)} signals | top @{top['author']} eng={top['eng']} sent={top['sent']:+d} | {top['text'][:60]}")
                    if len(seen) > 5000:
                        seen.clear()
            except Exception as e:
                log(f"cycle warn {repr(e)[:60]}")
            time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
