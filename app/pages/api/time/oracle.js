// file_id: SOM-TS-1000-v1.0.0 name: api/time/oracle.js description: Oracle API — the pre-committed 15M calls: current call + scored history + hit rate project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, oracle, predictions] created: 2026-08-04 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    const rows = await q("SELECT k, v FROM mc_state WHERE k IN ('oracle:current','oracle:history')");
    const out = {};
    for (const r of rows) {
      try { out[r.k.replace(":", "_")] = JSON.parse(r.v); } catch { out[r.k.replace(":", "_")] = null; }
    }
    const h = out.oracle_history || [];
    const scored = h.filter((c) => typeof c.won === "boolean");
    out.stats = {
      n: scored.length,
      hits: scored.filter((c) => c.won).length,
      rate: scored.length ? Math.round(100 * scored.filter((c) => c.won).length / scored.length) : null,
    };
    res.status(200).json(out);
  } catch (e) {
    res.status(200).json({ error: String(e).slice(0, 200) });
  }
}
