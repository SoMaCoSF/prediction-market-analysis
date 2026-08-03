// file_id: SOM-TS-0974-v1.0.0 name: api/trade/evidence.js description: Evidence API — the engine's verdicts (win-rate CI, expectancy, PROVEN/FORMING/DEAD) from mc_state project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, evidence, verdicts] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    const rows = await q("SELECT v, updated_at FROM mc_state WHERE k='evidence:lanes'");
    const ev = rows.length ? JSON.parse(rows[0].v) : null;
    res.status(200).json({ evidence: ev, updated_at: rows.length ? rows[0].updated_at : null });
  } catch (e) {
    res.status(200).json({ evidence: null, note: String(e).slice(0, 120) });
  }
}
