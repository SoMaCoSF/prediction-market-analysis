// file_id: SOM-TS-0982-v1.0.0 name: api/time/forecasts.js description: TIME forecasts — the news engine's supply-chain predictions with probabilities project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, time, forecasts, predictions] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    const rows = await q("SELECT v, updated_at FROM mc_state WHERE k='time:forecasts'");
    res.status(200).json({ forecasts: rows.length ? JSON.parse(rows[0].v) : [],
                           updated_at: rows.length ? rows[0].updated_at : null });
  } catch (e) {
    res.status(200).json({ forecasts: [], note: String(e).slice(0, 120) });
  }
}
