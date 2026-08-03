// file_id: SOM-TS-0954-v1.0.0 name: api/trade/shadow.js description: Shadow index API — latest shadow signals (whale prints) from the local stream via mc_state publish project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, shadow, index, whales] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    const rows = await q("SELECT v, updated_at FROM mc_state WHERE k='shadow:latest'");
    let latest = [];
    if (rows.length) {
      try { latest = JSON.parse(rows[0].v); } catch { latest = []; }
    }
    res.status(200).json({ latest, updated_at: rows.length ? rows[0].updated_at : null });
  } catch (e) {
    res.status(200).json({ latest: [], note: String(e).slice(0, 120) });
  }
}
