// file_id: SOM-TS-0970-v1.0.0 name: api/time/markets.js description: TIME markets — open Kalshi markets matching a topic keyword (the trade-on-the-news plane) project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, time, markets, topics] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
import { kalshiFetch } from "../../../lib/trade-kalshi";

const TOPIC_HINTS = {
  openai: "AI", anthropic: "AI", agents: "AI", models: "AI",
  nvidia: "NASDAQ", chips: "semiconductor",
  regulation: "AI Act", robotics: "robot",
};

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    const topic = String(req.query.topic || "");
    const r = await kalshiFetch("/markets?limit=100&status=open");
    const kw = (TOPIC_HINTS[topic] || topic || "").toLowerCase();
    const out = [];
    for (const m of r.markets || []) {
      const hay = `${m.ticker} ${m.title || ""} ${m.subtitle || ""}`.toLowerCase();
      if (kw && !hay.includes(kw)) continue;
      const ya = Math.round((m.yes_ask_dollars || 0) * 100);
      if (!(ya > 0 && ya < 100)) continue;
      out.push({
        ticker: m.ticker, title: (m.title || m.subtitle || "").slice(0, 80),
        ya, yb: Math.round((m.yes_bid_dollars || 0) * 100),
        vol: Math.round(parseFloat(m.volume_fp || 0) / 1000),
      });
      if (out.length >= 6) break;
    }
    res.status(200).json({ markets: out });
  } catch (e) {
    res.status(200).json({ markets: [], note: String(e).slice(0, 120) });
  }
}
