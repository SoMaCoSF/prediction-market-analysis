// file_id: SOM-TS-0967-v1.0.0 name: api/time/articles.js description: TIME articles — AI-topic feed from mc_state (published by the news engine) + vote counts project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, time, articles, ai] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    const rows = await q("SELECT v, updated_at FROM mc_state WHERE k='time:articles'");
    const arts = rows.length ? JSON.parse(rows[0].v) : [];
    const votes = await q("SELECT k, v FROM mc_state WHERE k LIKE 'time:vote:%'");
    const vc = {};
    for (const r of votes) vc[r.k.replace("time:vote:", "")] = Number(r.v) || 0;
    for (const a of arts) a.votes = vc[a.id] || 0;
    arts.sort((x, y) => (y.votes - x.votes) || (y.ts - x.ts));
    res.status(200).json({ articles: arts, updated_at: rows.length ? rows[0].updated_at : null });
  } catch (e) {
    res.status(200).json({ articles: [], note: String(e).slice(0, 120) });
  }
}
