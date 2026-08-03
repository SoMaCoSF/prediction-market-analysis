// file_id: SOM-TS-0986-v1.0.0 name: api/trade/poly.js description: Polymarket panel API — whale flow (shadow), divergences (xvenue), wallet leaderboard (copier), top poly markets project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, polymarket, whales, divergence, panel] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  const out = { shadow: [], divergences: [], board: [] };
  try {
    const rows = await q("SELECT k, v, updated_at FROM mc_state WHERE k IN ('shadow:latest','xvenue:latest','copier:board')");
    for (const r of rows) {
      if (r.k === "shadow:latest") out.shadow = JSON.parse(r.v || "[]");
      if (r.k === "xvenue:latest") out.divergences = JSON.parse(r.v || "[]");
      if (r.k === "copier:board") out.board = JSON.parse(r.v || "[]");
    }
  } catch (e) {
    out.note = String(e).slice(0, 120);
  }
  res.status(200).json(out);
}
