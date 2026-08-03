// file_id: SOM-TS-0948-v1.0.0 name: api/trade/fleet.js description: Fleet health API — daemon heartbeats from mc_state (daemon:* keys) + ages project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, fleet, daemons, health] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  try {
    const rows = await q("SELECT k, v, updated_at FROM mc_state WHERE k LIKE 'daemon:%' ORDER BY k");
    const now = Date.now();
    const daemons = rows.map((r) => ({
      name: r.k.replace("daemon:", ""),
      state: r.v,
      age_s: Math.max(0, Math.round((now - new Date(r.updated_at).getTime()) / 1000)),
    }));
    res.status(200).json({ daemons, ts: Math.round(now / 1000) });
  } catch (e) {
    res.status(200).json({ daemons: [], note: String(e).slice(0, 120) });
  }
}
