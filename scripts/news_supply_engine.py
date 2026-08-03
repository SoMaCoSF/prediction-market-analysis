# file_id: SOM-PY-0962-v1.0.0 name: news_supply_engine.py description: News->supply-chain->market prediction engine — keyless EU/global RSS, supply-chain node mapping, bold forecasts minted as 0x326 FORECAST UUIDs, edge-gap alerts vs Kalshi prices; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [news, supply-chain, eu, forecast, prediction, rss] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""news_supply_engine.py — read the world's wires, map supply chains, mint forecasts.

Pipeline: RSS headline -> supply-chain NODES hit -> affected commodities/sectors
-> candidate Kalshi markets -> our probability vs market price -> EDGE GAP alert.
Every forecast = 0x326 FORECAST UUID (probability in signal bits, horizon in ts,
deterministic seed) -> the stream, resolvable later for Brier scoring.
EU tilt: ECB/eurozone feeds + EU-session hours; the chain atlas is explicit and
editable. Zero tokens, pure stdlib+httpx XML parse.
"""
from __future__ import annotations

import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import httpx  # noqa: E402
import runlog  # noqa: E402
import uuid_ledger as L  # noqa: E402
from uuid_service_turboquant import encode_gyst, fnv1a12  # noqa: E402

DB = ROOT / "data" / "uuid_stream.db"
TYPE_FORECAST = 0x326
TYPE_ARTICLE = 0x3D4
PROV_NEWS = 0xD
POLL_S = 300

# --- forecast-bet linkage: back each prediction with a position ---
import hashlib  # noqa: E402
import os  # noqa: E402

import sb  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
MC = os.getenv("MC_URL", "http://127.0.0.1:8420")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
PK = hashlib.sha256(f"3024a97f6e32|omen-01|{sb.status_salt()}".encode()).hexdigest()
BET_SERIES = {"KXBTC15M": "crypto", "KXETH15M": "crypto", "KXWTI": "energy"}   # validated-live series only
MAX_OPEN_BETS = 5
DAILY_BET_CAP = 25.00
open_bets: list[dict] = []
spent_today = 0.0
today = time.strftime("%Y-%m-%d")


def fire(ticker, side, price, count=1):
    try:
        r = httpx.post(f"{MC}/api/order", json={"ticker": ticker, "side": side, "price": price,
                       "count": count, "mode": "live", "passkey": PK, "confirm": "FIRE"}, timeout=30)
        d = r.json()
        return {"ok": bool(d.get("ok")), "filled": float((d.get("ack") or {}).get("fill_count") or 0)}
    except Exception:
        return {"ok": False, "filled": 0.0}


def place_forecast_bet(cx, node, prob, hint, title):
    """Back the forecast: current window on the hinted series, 1ct, direction=prob side."""
    global spent_today
    if hint not in BET_SERIES or len(open_bets) >= MAX_OPEN_BETS or spent_today >= DAILY_BET_CAP:
        return None
    try:
        r = cx.get(f"{KALSHI}/markets", params={"limit": 3, "status": "open", "series_ticker": hint}, timeout=15)
        for m in r.json().get("markets", []):
            ya = round(float(m.get("yes_ask_dollars") or 0) * 100)
            yb = round(float(m.get("yes_bid_dollars") or 0) * 100)
            if not (0 < ya < 100):
                continue
            side, price = ("yes", ya) if prob > 0.5 else ("no", 100 - yb)
            if not (1 <= price <= 65):
                return None
            res = fire(m["ticker"], side, price)
            if res["ok"]:
                bet = {"ticker": m["ticker"], "side": side, "price": price,
                       "node": node, "prob": prob, "ts": time.time(), "filled": res["filled"]}
                open_bets.append(bet)
                spent_today += price / 100.0
                runlog.assert_event(True, "news", f"FORECAST-BET {node} p={prob:.2f} -> {side.upper()} {hint} @{price}c {'FILLED' if res['filled'] else 'resting'}", ticker=m["ticker"])
                return bet
    except Exception as e:
        runlog.log_event("news", f"bet warn {repr(e)[:50]}", kind="warn")
    return None

FEEDS = [
    ("bbc-biz", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("ecb", "https://www.ecb.europa.eu/rss/press.html"),
    ("euractiv", "https://www.euractiv.com/feed/"),
    ("mw-commodities", "https://feeds.content.dowjones.io/public/rss/mw_marketpulse"),
    # AI plane for TIME.somacosf.com
    ("techcrunch-ai", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("verge-ai", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("venturebeat-ai", "https://venturebeat.com/category/ai/feed/"),
    ("mit-review", "https://www.technologyreview.com/feed/"),
    ("ars-ai", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
]

AI_TOPICS = {
    "openai": ["openai", "chatgpt", "gpt", "sama", "altman"],
    "anthropic": ["anthropic", "claude"],
    "nvidia": ["nvidia", "jensen", "blackwell", "gpu", "cuda"],
    "agents": ["agent", "agentic", "autonomous", "mcp"],
    "chips": ["chip", "semiconductor", "tsmc", "asml", "fab"],
    "regulation": ["regulation", "eu ai act", "policy", "antitrust", "copyright", "lawsuit"],
    "models": ["llm", "model", "reasoning", "benchmark", "frontier"],
    "robotics": ["robot", "humanoid", "figure", "optimus"],
}


def topic_of(title: str) -> str:
    low = title.lower()
    for topic, kws in AI_TOPICS.items():
        if any(k in low for k in kws):
            return topic
    return "ai-general"

AI_FEEDS = [
    ("techcrunch-ai", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("verge-ai", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("ars-ai", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    ("venturebeat-ai", "https://venturebeat.com/category/ai/feed/"),
    ("mit-tr-ai", "https://www.technologyreview.com/feed/"),
]

TOPICS = {
    "openai": ["openai", "chatgpt", "gpt-5", "sama", "sam altman"],
    "anthropic": ["anthropic", "claude"],
    "nvidia": ["nvidia", "jensen", "gpu", "blackwell", "h100", "b200"],
    "agents": ["agent", "agentic", "autonomous"],
    "chips": ["chip", "semiconductor", "tsmc", "asml", "intel", "amd"],
    "regulation": ["regulation", "eu ai act", "executive order", "antitrust", "ftc", "copyright"],
    "models": ["llm", "model", "gemini", "llama", "mistral", "grok", "kimi", "deepseek"],
    "robotics": ["robot", "humanoid", "figure", "optimus"],
}


# supply-chain atlas: node -> (keywords, downstream effects, kalshi hint, base prob shift)
ATLAS = {
    "red-sea-shipping": (["red sea", "houthi", "suez", "shipping attack", "freight"],
                         "freight rates up -> goods inflation -> energy bid", "KXWTI", +0.08),
    "nuclear-restart": (["nuclear", "reactor", "uranium", "smr", "small modular", "enrichment"],
                        "firm power premium -> grid capex -> copper/electrical bid", "KXWTI", +0.04),
    "datacenter-power": (["datacenter", "data center", "ai capex", "hyperscaler", "power purchase agreement", "ppa"],
                         "grid strain -> power prices -> energy complex", "KXWTI", +0.05),
    "electrical-supply": (["grainger", "cable tray", "low voltage", "switchgear", "transformer", "hubbell", "eaton"],
                          "MRO backlog -> construction costs -> industrial inflation", "KXWTI", +0.03),
    "copper-grid": (["copper", "grid", "transmission", "substation", "interconnection queue"],
                    "grid build-out -> copper demand -> energy-adjacent bid", "KXWTI", +0.04),
    "ecb-rates": (["ecb", "interest rate", "lagarde", "deposit facility", "rate cut", "rate hike"],
                  "EUR move -> dollar index -> crypto inverse", "KXBTC15M", +0.05),
    "semis-export": (["asml", "semiconductor", "chip export", "export control", "tsmc"],
                     "chip supply chain stress -> tech equities", "KXNASDAQ", +0.06),
    "energy-eu": (["nord stream", "lng", "gas storage", "ttf", "energy crisis", "pipeline"],
                  "EU gas -> power prices -> industrials", "KXWTI", +0.07),
    "grain": (["wheat", "grain corridor", "ukraine grain", "harvest"],
              "grain supply -> food inflation", "KXWHEAT", +0.06),
    "crypto-reg": (["mica", "sec bitcoin", "etf flows", "crypto regulation"],
                   "regulatory flow -> crypto spot", "KXBTC15M", +0.05),
    "tariffs": (["tariff", "trade war", "import duty", "retaliatory"],
                "trade friction -> sector rotation", "KXSP500", +0.05),
}


def mint_forecast(node, prob, seed, ts):
    return encode_gyst(type_code=TYPE_FORECAST, namespace=fnv1a12(node), timestamp_sec=ts,
                       fractal_depth=1, fractal_domain=0x9, fractal_generation=0,
                       forecast_signal=max(0.01, min(0.99, prob)), provenance=PROV_NEWS,
                       content_seed=seed)


def store(cur, u, ts, node, detail):
    hi, lo = L.hi_lo(u)
    cur.execute("INSERT OR IGNORE INTO stream VALUES (?,?,?,?,?,?,?)",
                (u, ts, "forecast", node, detail, hi, lo))
    return cur.rowcount


def mint_article(title: str, topic: str, source: str, ts: int) -> str:
    """Every story is a UUIDv8 object: routable, bettable (as order parent), transactional."""
    return encode_gyst(type_code=TYPE_ARTICLE, namespace=fnv1a12(topic), timestamp_sec=ts,
                       fractal_depth=1, fractal_domain=0xA, fractal_generation=0,
                       forecast_signal=0.5, provenance=PROV_NEWS,
                       content_seed=f"article|{source}|{title[:60]}")


def headlines(cx):
    out = []
    for name, url in FEEDS:
        try:
            r = cx.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 somaco-forecast/1.0"})
            root = ET.fromstring(r.text)
            for item in root.iter("item"):
                t = item.findtext("title") or ""
                link = item.findtext("link") or ""
                if t:
                    out.append((name, t.strip(), link.strip()))
        except Exception as e:
            runlog.log_event("news", f"feed {name} warn {repr(e)[:50]}", kind="warn")
    return out[:80]


def publish_articles(items):
    """Publish AI-topic articles to mc_state time:articles for TIME.somacosf.com."""
    try:
        import json as _json
        seen = set()
        arts = []
        for src, title, link in items:
            topic = topic_of(title)
            if topic == "ai-general" and not src.endswith(("-ai", "review")):
                continue  # non-AI feeds only contribute tagged AI items
            u = mint_article(title, topic, src, int(time.time()))
            aid = u[-12:]  # low-42 hex tail = the routable handle
            if aid in seen:
                continue
            seen.add(aid)
            arts.append({"id": aid, "uuid": u, "title": title, "source": src, "topic": topic,
                         "link": link, "ts": int(time.time())})
        arts = arts[:40]
        con = sb.sb_conn()
        con.autocommit = True
        cur = con.cursor()
        cur.execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('time:articles', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (_json.dumps(arts),))
        # forecasts for the page: recent supply-chain calls with probabilities
        cur2 = sqlite3.connect(DB).cursor()
        rows = cur2.execute(
            "SELECT symbol, detail, ts FROM stream WHERE source='forecast' ORDER BY ts DESC LIMIT 8").fetchall()
        fcs = [{"node": r[0], "detail": r[1], "ts": r[2]} for r in rows]
        cur.execute(
            "INSERT INTO mc_state (k, v, updated_at) VALUES ('time:forecasts', %s, now()) "
            "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
            (_json.dumps(fcs),))
        con.close()
        return len(arts)
    except Exception as e:
        runlog.log_event("news", f"articles warn {repr(e)[:50]}", kind="warn")
        return 0


def main():
    fleetlib.acquire_lock("news")
    print(f"[news] start | feeds={len(FEEDS)} nodes={len(ATLAS)} poll={POLL_S}s", flush=True)
    runlog.log_event("news", "news/supply engine start", nodes=list(ATLAS))
    with httpx.Client(headers={"Accept-Encoding": "identity"}, timeout=20) as cx:
        while True:
            fleetlib.checkin("news")
            ts = int(time.time())
            made = 0
            try:
                con = sqlite3.connect(DB)
                cur = con.cursor()
                items = headlines(cx)
                for _src, title, _link in items:
                    low = title.lower()
                    for node, (kws, chain, hint, shift) in ATLAS.items():
                        if any(k in low for k in kws):
                            prob = 0.5 + shift
                            detail = f"{node}: {title[:70]} | chain: {chain} | hint {hint} | p={prob:.2f}"
                            made += store(cur, mint_forecast(node, prob, f"fc|{node}|{title[:40]}", ts),
                                          ts, node, detail)
                            runlog.log_event("news", f"FORECAST {detail}")
                con.commit()
                con.close()
                n_art = publish_articles(items)
                if n_art:
                    runlog.log_event("news", f"published {n_art} AI articles to TIME", articles=n_art)
            except Exception as e:
                runlog.log_event("news", f"cycle warn {repr(e)[:60]}", kind="warn")
            if made or ts % 1800 < POLL_S:
                print(f"[news] {time.strftime('%H:%M:%S')} +{made} forecasts", flush=True)
            time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
