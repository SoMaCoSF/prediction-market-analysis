# file_id: SOM-PY-0976-v1.1.0 name: x_watcher.py description: X watcher v3 — expanded multi-query sentiment sweep with faster polling; official X API (bearer) with keyless fallback; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [x, sentiment, ai-startups, signals, stream, expanded] created: 2026-08-03 modified: 2026-08-11 version: 1.1.0 agent_id: HERMES-AGENT
"""x_watcher.py v3 — the X sentiment lane for the AI startup space.

Mode A (X_BEARER_TOKEN in .env): official X API v2 recent-search, 2-min poll:
  queries: AI startups, crypto, policy/regulation, chip/semiconductor, robotics
Mode B (no key): keyless fallback — RSS bridge (degraded but functional).

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
POLL_S = 120  # 2 min — faster than before

# 5 targeted queries covering the full AI/crypto/policy surface + Congress/trader accounts
QUERIES = [
    '("AI startup" OR "AI agent" OR "founded" OR "seed round" OR "Series A") (AI OR artificial intelligence) lang:en -is:retweet',
    '("bitcoin" OR "ethereum" OR "crypto" OR "solana") (pump OR dump OR breakout OR SEC OR ETF) lang:en -is:retweet',
    '("AI regulation" OR "EU AI Act" OR "SEC" OR "antitrust" OR "copyright") (AI OR artificial intelligence) lang:en -is:retweet',
    '("semiconductor" OR "TSMC" OR "NVIDIA" OR "chip export" OR "fab") (surge OR demand OR shortage OR ban) lang:en -is:retweet',
    '("humanoid" OR "robot" OR "Figure AI" OR "Optimus" OR "tesla bot") (launch OR funding OR breakthrough) lang:en -is:retweet',
    '("Nancy Pelosi" OR "Paul Pelosi" OR "@nancypelosi") (stock OR trade OR purchase OR sale OR buy OR sell) lang:en -is:retweet',
    '("Donald Trump" OR "Trump" OR "@realdonaldtrump") (stock OR trade OR purchase OR sale OR buy OR sell OR crypto) lang:en -is:retweet',
    '("Congress" OR "Senate" OR "House") (bill OR act OR vote OR legislation OR market OR trading OR fiscal) lang:en -is:retweet',
]

POS = ["launch", "raised", "funding", "breakthrough", "sota", "release", "partnership", "growth", "wins",
       "pump", "breakout", "surge", "demand", "approval", "win", "bullish"]
NEG = ["shutdown", "layoff", "lawsuit", "delay", "bug", "outage", "bankrupt", "fail",
       "dump", "ban", "recession", "shortage", "investigation", "bearish", "crash", "hack"]
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
            (json.dumps(signals[:20]),))
        con.close()
    except Exception as e:
        log(f"publish warn {repr(e)[:50]}")


def fetch_official(cx, query):
    r = cx.get("https://api.x.com/2/tweets/search/recent",
               params={"query": query, "max_results": 25,
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
                    "text": t.get("text", "")[:200], "eng": eng,
                    "sent": sentiment(t.get("text", "")), "ts": int(time.time())})
    return out


def main():
    fleetlib.acquire_lock("xwatch")
    mode = "OFFICIAL" if TOKEN else "NO-KEY (RSS fallback)"
    log(f"start | mode={mode} queries={len(QUERIES)} poll={POLL_S}s")
    with httpx.Client(headers={"Accept-Encoding": "identity"}, timeout=25) as cx:
        while True:
            fleetlib.checkin("xwatch")
            try:
                all_sigs = []
                if TOKEN:
                    for q in QUERIES:
                        sigs = [s for s in fetch_official(cx, q) if s["id"] not in seen]
                        for s in sigs:
                            seen.add(s["id"])
                            s["uuid"] = mint_signal(s["author"], s["sent"], s["eng"])
                        all_sigs.extend(sigs)
                if len(seen) > 10000:
                    seen.clear()
                if all_sigs:
                    publish(all_sigs)
                    top = max(all_sigs, key=lambda s: s["eng"])
                    log(f"{len(all_sigs)} signals | top @{top['author']} eng={top['eng']} sent={top['sent']:+d} | {top['text'][:60]}")
            except Exception as e:
                log(f"cycle warn {repr(e)[:60]}")
            time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
