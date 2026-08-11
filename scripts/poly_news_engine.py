# file_id: SOM-PY-0991-v1.0.0 name: polymarket_news_engine.py description: Polymarket news/events/signals ingestor — Gamma API keyless reader that mints 0x3D6 SIGNAL UUIDs into the local stream; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [polymarket, gamma, news, events, signals, zero-token] created: 2026-08-11 version: 1.0.0 agent_id: HERMES-AGENT
"""polymarket_news_engine.py — read Polymarket's Gamma API, mint signals.

Pulls active markets + events from gamma-api.polymarket.com (keyless, no geoblock
for data reads). Categorizes by AI/ML topic, computes simple momentum from
outcomePrices history, and mints 0x3D6 SIGNAL UUIDs into the local stream.
Also publishes a curated top-20 list to mc_state poly:latest for the dashboard.
Zero model tokens.
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
import uuid_ledger as L  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from uuid_service_turboquant import encode_gyst, fnv1a12  # noqa: E402

load_dotenv(ROOT / ".env")

DB = ROOT / "data" / "uuid_stream.db"
TYPE_SIGNAL = 0x3D6
PROV_POLY = 0xF
POLL_S = 180
GAMMA = "https://gamma-api.polymarket.com"

# AI/ML topic clusters for signal categorization
AI_CLUSTERS = {
    "openai": ["openai", "chatgpt", "gpt-5", "gpt-4", "sama", "altman", "o1", "o3"],
    "anthropic": ["anthropic", "claude", "sonnet"],
    "google": ["gemini", "deepmind", "google ai"],
    "nvidia": ["nvidia", "jensen", "blackwell", "h100", "b200", "cuda", "gpu"],
    "meta": ["meta ai", "llama", "zuckerberg"],
    "xai": ["xai", "grok", "musk ai"],
    "agents": ["agent", "agentic", "autonomous", "mcp", "a2a"],
    "robotics": ["robot", "humanoid", "figure", "optimus", "tesla bot"],
    "chips": ["semiconductor", "tsmc", "asml", "intel", "amd", "chip export", "fab"],
    "regulation": ["sec", "ftc", "antitrust", "eu ai act", "regulation", "copyright", "lawsuit"],
    "models": ["llm", "reasoning", "benchmark", "frontier model", "deepseek", "mistral", "kimi"],
    "crypto": ["bitcoin", "ethereum", "solana", "btc", "eth", "sol", "xrp", "crypto"],
}


def topic_of(text: str) -> str:
    low = text.lower()
    for topic, kws in AI_CLUSTERS.items():
        if any(k in low for k in kws):
            return topic
    return "other"


def mint_signal_uuid(topic: str, strength: float, seed: str, ts: int) -> str:
    return encode_gyst(
        type_code=TYPE_SIGNAL,
        namespace=fnv1a12(topic),
        timestamp_sec=ts,
        fractal_depth=1,
        fractal_domain=0xC,
        fractal_generation=0,
        forecast_signal=max(0.0, min(1.0, strength)),
        provenance=PROV_POLY,
        content_seed=seed,
    )


def store_signal(cur, uuid_str, ts, topic, detail):
    hi, lo = L.hi_lo(uuid_str)
    cur.execute(
        "INSERT OR IGNORE INTO stream VALUES (?,?,?,?,?,?,?)",
        (uuid_str, ts, "signal", topic, detail, hi, lo),
    )
    return cur.rowcount


def fetch_active_markets(cx):
    """Fetch top-volume active Polymarket markets via Gamma."""
    out = []
    try:
        r = cx.get(
            f"{GAMMA}/markets",
            params={"limit": 200, "order": "volume24hr", "active": "true"},
            timeout=20,
        )
        if r.status_code == 200:
            out = r.json()
            if isinstance(out, dict):
                out = out.get("data", out.get("markets", []))
    except Exception as e:
        runlog.log_event("polynews", f"markets warn {repr(e)[:50]}", kind="warn")
    return out


def fetch_events(cx):
    """Fetch top-volume active Polymarket events."""
    out = []
    try:
        r = cx.get(
            f"{GAMMA}/events",
            params={"limit": 100, "order": "volume24hr", "active": "true"},
            timeout=20,
        )
        if r.status_code == 200:
            out = r.json()
            if isinstance(out, dict):
                out = out.get("data", out.get("events", []))
    except Exception as e:
        runlog.log_event("polynews", f"events warn {repr(e)[:50]}", kind="warn")
    return out


def score_market(m: dict) -> tuple[str, float, str]:
    """Return (topic, signal_strength 0-1, detail_text)."""
    q = m.get("question") or m.get("title") or ""
    desc = m.get("description") or ""
    text = f"{q} {desc}"
    topic = topic_of(text)
    vol = float(m.get("volume24hr") or m.get("volume") or 0)
    liq = float(m.get("liquidity") or 0)
    prices = m.get("outcomePrices") or "[]"
    if isinstance(prices, str):
        try:
            prices = json.loads(prices)
        except Exception:
            prices = []
    best_p = 0.0
    if prices and isinstance(prices, list):
        try:
            best_p = max(float(x) for x in prices if x is not None)
        except Exception:
            pass
    # strength = blend of volume prominence + AI relevance + price extremeness
    vol_score = min(1.0, vol / 1_000_000.0)
    liq_score = min(1.0, liq / 500_000.0)
    edge = abs(best_p - 0.5) * 2  # 0=50/50, 1=extreme
    strength = (0.5 * vol_score + 0.3 * liq_score + 0.2 * edge)
    if topic == "other":
        strength *= 0.3  # downgrade non-AI
    detail = f"{topic}: {q[:80]} | vol=${vol:,.0f} liq=${liq:,.0f} p={best_p:.2f}"
    return topic, strength, detail


def score_event(ev: dict) -> tuple[str, float, str]:
    title = ev.get("title") or ev.get("slug") or ""
    vol = float(ev.get("volume") or ev.get("volume24hr") or 0)
    liq = float(ev.get("liquidity") or 0)
    topic = topic_of(title)
    vol_score = min(1.0, vol / 2_000_000.0)
    liq_score = min(1.0, liq / 1_000_000.0)
    strength = 0.6 * vol_score + 0.4 * liq_score
    if topic == "other":
        strength *= 0.3
    detail = f"EVENT {topic}: {title[:80]} | vol=${vol:,.0f} liq=${liq:,.0f}"
    return topic, strength, detail


def publish_signals(signals):
    try:
        con = sb.sb_conn()
        con.autocommit = True
        payload = signals[:25]
        con.cursor().execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('poly:latest', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (json.dumps(payload),),
        )
        con.close()
    except Exception as e:
        runlog.log_event("polynews", f"publish warn {repr(e)[:50]}", kind="warn")


def main():
    fleetlib.acquire_lock("polynews")
    print("[polynews] start | Gamma keyless ingestor", flush=True)
    runlog.log_event("polynews", "polymarket news engine start")
    with httpx.Client(headers={"Accept-Encoding": "identity"}, timeout=25) as cx:
        while True:
            fleetlib.checkin("polynews")
            ts = int(time.time())
            made = 0
            try:
                con = sqlite3.connect(DB)
                cur = con.cursor()
                signals = []
                # markets
                markets = fetch_active_markets(cx)
                for m in markets:
                    mid = m.get("id") or m.get("slug") or ""
                    topic, strength, detail = score_market(m)
                    if strength < 0.15:
                        continue
                    u = mint_signal_uuid(topic, strength, f"poly|{mid}", ts)
                    made += store_signal(cur, u, ts, topic, detail)
                    signals.append(
                        {
                            "uuid": u,
                            "topic": topic,
                            "strength": round(strength, 3),
                            "source": "gamma:market",
                            "title": (m.get("question") or m.get("title") or "")[:80],
                            "vol": float(m.get("volume24hr") or m.get("volume") or 0),
                            "ts": ts,
                        }
                    )
                # events
                events = fetch_events(cx)
                for ev in events:
                    eid = ev.get("id") or ev.get("slug") or ""
                    topic, strength, detail = score_event(ev)
                    if strength < 0.15:
                        continue
                    u = mint_signal_uuid(topic, strength, f"polyev|{eid}", ts)
                    made += store_signal(cur, u, ts, topic, detail)
                    signals.append(
                        {
                            "uuid": u,
                            "topic": topic,
                            "strength": round(strength, 3),
                            "source": "gamma:event",
                            "title": (ev.get("title") or "")[:80],
                            "vol": float(ev.get("volume") or ev.get("volume24hr") or 0),
                            "ts": ts,
                        }
                    )
                # dedupe by title, keep strongest
                by_title = {}
                for s in signals:
                    t = s["title"].lower().strip()
                    if t not in by_title or s["strength"] > by_title[t]["strength"]:
                        by_title[t] = s
                signals = sorted(by_title.values(), key=lambda x: -x["strength"])[:30]
                con.commit()
                con.close()
                if signals:
                    publish_signals(signals)
                if made or ts % 600 < POLL_S:
                    top_topic = signals[0]["topic"] if signals else "-"
                    print(f"[polynews] {time.strftime('%H:%M:%S')} +{made} signals | top={top_topic}", flush=True)
            except Exception as e:
                runlog.log_event("polynews", f"cycle warn {repr(e)[:60]}", kind="warn")
            time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
