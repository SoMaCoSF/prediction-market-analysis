// file_id: SOM-TS-1006-v1.0.0 name: api/trade/bridge.js description: Bridge API — cross-account funding awareness: Kalshi cash + Poly USDC + the current recommendation and message. project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, bridge, funding, polymarket, kalshi] created: 2026-08-04 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    const rows = await q("SELECT k, v FROM mc_state WHERE k IN ('bridge:state','poly:exec','vault:state')");
    const out = {};
    for (const r of rows) {
      try { out[r.k.replace(":", "_")] = JSON.parse(r.v); } catch { out[r.k.replace(":", "_")] = null; }
    }
    res.status(200).json(out);
  } catch (e) {
    res.status(200).json({ error: String(e).slice(0, 200) });
  }
}
