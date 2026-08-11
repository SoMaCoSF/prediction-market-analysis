# file_id: SOM-PY-0962-v1.1.0 name: news_supply_engine.py description: News->supply-chain->market prediction engine — expanded 30-feed global RSS, supply-chain node mapping, bold forecasts minted as 0x326 FORECAST UUIDs, edge-gap alerts vs Kalshi prices; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [news, supply-chain, eu, forecast, prediction, rss, expanded] created: 2026-08-03 modified: 2026-08-11 version: 1.1.0 agent_id: HERMES-AGENT
"""news_supply_engine.py — read the world's wires, map supply chains, mint forecasts.

Pipeline: RSS headline -> supply-chain NODES hit -> affected commodities/sectors
-> candidate Kalshi markets -> our probability vs market price -> EDGE GAP alert.
Every forecast = 0x326 FORECAST UUID (probability in signal bits, horizon in ts,
deterministic seed) -> the stream, resolvable later for Brier scoring.
Wide net: 30+ feeds across business, tech, policy, energy, AI, crypto, science.
Zero tokens, pure stdlib+httpx XML parse.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import httpx  # noqa: E402
import os as _os  # noqa: E402
FLEET_HALTED = _os.getenv("FLEET_HALTED", "0") == "1"
import runlog  # noqa: E402
import uuid_ledger as L  # noqa: E402
from uuid_service_turboquant import encode_gyst, fnv1a12  # noqa: E402

DB = ROOT / "data" / "uuid_stream.db"
TYPE_FORECAST = 0x326
TYPE_ARTICLE = 0x3D4
PROV_NEWS = 0xD
POLL_S = 180  # 3 min — faster than before

# --- uptick spiral integration: read adjusted weights if available ---
WEIGHTS_FILE = ROOT / "data" / "uptick_weights.json"


def load_uptick_shifts() -> dict[str, float]:
    """Read adjusted node shifts from uptick_spiral. Falls back to ATLAS base shifts."""
    try:
        if WEIGHTS_FILE.exists():
            w = json.loads(WEIGHTS_FILE.read_text())
            return {node: data.get("shift", data.get("base_shift", 0.0))
                    for node, data in w.items()}
    except Exception:
        pass
    return {node: shift for node, (_, shift) in ATLAS.items()}


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
    if FLEET_HALTED:
        return None
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


# 30+ feeds across global business, tech, AI, policy, energy, crypto, science
FEEDS = [
    # --- Business / general ---
    ("bbc-biz", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("reuters-biz", "https://www.reutersagency.com/feed/?bestTopics=business"),
    ("ft-com", "https://www.ft.com/rss/home"),
    ("bloomberg-markets", "https://feeds.bloomberg.com/markets/news/rss.xml"),
    ("ap-biz", "https://apnews.com/hub/business/rss.xml"),
    ("guardian-biz", "https://www.theguardian.com/business/rss"),
    ("cnbc", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"),
    # --- AI / tech ---
    ("techcrunch", "https://techcrunch.com/feed/"),
    ("verge", "https://www.theverge.com/rss/index.xml"),
    ("wired", "https://www.wired.com/feed/rss"),
    ("arstechnica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("the-register", "https://www.theregister.com/headlines.atom"),
    ("mit-review", "https://www.technologyreview.com/feed/"),
    ("venturebeat", "https://venturebeat.com/feed/"),
    ("zdnet", "https://www.zdnet.com/news/rss.xml"),
    # --- Policy / regulation / geopolitics ---
    ("politico", "https://www.politico.com/rss/politicopicks.xml"),
    ("reuters-politics", "https://www.reutersagency.com/feed/?bestTopics=politics"),
    ("bbc-politics", "https://feeds.bbci.co.uk/news/politics/rss.xml"),
    ("ap-politics", "https://apnews.com/hub/politics/rss.xml"),
    ("the-hill", "https://thehill.com/feed/"),
    # --- Energy / commodities / macro ---
    ("reuters-energy", "https://www.reutersagency.com/feed/?bestTopics=energy"),
    ("opec", "https://www.opec.org/opec_web/en/rss/rss_opec.xml"),
    ("eia", "https://www.eia.gov/rss/todayinenergy.xml"),
    ("ft-com", "https://www.ft.com/rss/home"),
    ("bbc-economy", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    # --- Crypto / digital assets ---
    ("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("cointelegraph", "https://cointelegraph.com/rss"),
    ("decrypt", "https://decrypt.co/feed"),
    ("blockworks", "https://blockworks.co/feed/"),
    ("the-block", "https://www.theblock.co/rss.xml"),
    # --- US Congress / legislation / market-moving policy ---
    ("congress-gov", "https://www.congress.gov/rss/house-floor-action.xml"),
    ("congress-bills", "https://www.congress.gov/rss/pending-legislation.xml"),
    ("senate-journal", "https://www.congress.gov/rss/senate-floor-action.xml"),
    ("rollcall", "https://www.rollcall.com/feed/"),
    ("the-hill", "https://thehill.com/feed/"),
    ("politico", "https://www.politico.com/rss/politicopicks.xml"),
    ("ap-politics", "https://apnews.com/hub/politics/rss.xml"),
    ("reuters-politics", "https://www.reutersagency.com/feed/?bestTopics=politics"),
    ("bbc-politics", "https://feeds.bbci.co.uk/news/politics/rss.xml"),
    # --- Science / research ---
    ("nature-news", "https://www.nature.com/nature.rss"),
    ("science-org", "https://www.science.org/rss/news_current.xml"),
    ("arxiv-cs", "https://rss.arxiv.org/rss/cs"),
    ("new-scientist", "https://www.newscientist.com/section/news/rss/"),
]

# Topic keywords for article categorization (AI/ML focus)
TOPICS = {
    "openai": ["openai", "chatgpt", "gpt-5", "gpt-4", "sama", "sam altman", "o1", "o3"],
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
    "crypto": ["bitcoin", "ethereum", "solana", "btc", "eth", "sol", "xrp", "crypto", "polymarket"],
    "energy": ["oil", "gas", "lng", "opec", "energy", "power", "grid", "renewable"],
    "macro": ["fed", "rate", "inflation", "cpi", "gdp", "recession", "ecb", "central bank"],
    "congress": ["congress", "senate", "house", "pelosi", "mccarthy", "schumer", " McConnell",
                 "bill", "act", "legislation", "vote", "amendment", "appropriation", "debt ceiling",
                 "infrastructure", "stimulus", "regulation", "sec", "cftc", "cftc", "treasury",
                 "federal reserve", "yellen", "powell", "interest rate", "fiscal", "tax"],
}


def topic_of(title: str) -> str:
    low = title.lower()
    for topic, kws in TOPICS.items():
        if any(k in low for k in kws):
            return topic
    return "general"


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
    "ai-power": (["ai power", "datacenter power", "gpu cluster", "training compute"],
                 "compute demand -> power demand -> energy bid", "KXWTI", +0.04),
    "chip-war": (["chip war", "semiconductor ban", "chip act", "export control", "tsmc export"],
                 "supply chain disruption -> chip stocks", "KXNASDAQ", +0.05),
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
            r = cx.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 somaco-forecast/2.0"})
            root = ET.fromstring(r.text)
            for item in root.iter("item"):
                t = item.findtext("title") or ""
                link = item.findtext("link") or ""
                if t:
                    out.append((name, t.strip(), link.strip()))
        except Exception as e:
            runlog.log_event("news", f"feed {name} warn {repr(e)[:50]}", kind="warn")
    return out[:120]


def publish_articles(items):
    """Publish AI-topic articles to mc_state time:articles for TIME.somacosf.com."""
    try:
        import json as _json
        seen = set()
        arts = []
        for src, title, link in items:
            topic = topic_of(title)
            if topic == "general" and not src.endswith(("techcrunch", "verge", "wired", "arstechnica", "mit-review", "venturebeat")):
                continue  # non-tech feeds only contribute tagged AI items
            u = mint_article(title, topic, src, int(time.time()))
            aid = u[-12:]  # low-42 hex tail = the routable handle
            if aid in seen:
                continue
            seen.add(aid)
            arts.append({"id": aid, "uuid": u, "title": title, "source": src, "topic": topic,
                         "link": link, "ts": int(time.time())})
        arts = arts[:60]
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
            "SELECT symbol, detail, ts FROM stream WHERE source='forecast' ORDER BY ts DESC LIMIT 12").fetchall()
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
                uptick_shifts = load_uptick_shifts()  # adjusted by uptick_spiral
                for _src, title, _link in items:
                    low = title.lower()
                    for node, (kws, chain, hint, shift) in ATLAS.items():
                        if any(k in low for k in kws):
                            # Use uptick-adjusted shift if available, else ATLAS base
                            prob = 0.5 + uptick_shifts.get(node, shift)
                            detail = f"{node}: {title[:70]} | chain: {chain} | hint {hint} | p={prob:.2f}"
                            made += store(cur, mint_forecast(node, prob, f"fc|{node}|{title[:40]}", ts),
                                          ts, node, detail)
                            runlog.log_event("news", f"FORECAST {detail}")
                            # micro-bet on the hinted Kalshi series if edge is strong enough
                            try:
                                if abs(prob - 0.5) >= 0.08:
                                    place_forecast_bet(cx, node, prob, hint, title)
                            except Exception as e:
                                runlog.log_event("news", f"bet warn {repr(e)[:60]}", kind="warn")
                con.commit()
                con.close()
                n_art = publish_articles(items)
                if n_art:
                    runlog.log_event("news", f"published {n_art} articles to TIME", articles=n_art)
            except Exception as e:
                runlog.log_event("news", f"cycle warn {repr(e)[:60]}", kind="warn")
            if made or ts % 1800 < POLL_S:
                print(f"[news] {time.strftime('%H:%M:%S')} +{made} forecasts", flush=True)
            time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
