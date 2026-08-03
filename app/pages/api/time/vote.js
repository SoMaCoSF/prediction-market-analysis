// file_id: SOM-TS-0968-v1.0.0 name: api/time/vote.js description: TIME voting — POST {id, dir} increments the article/topic vote counter in mc_state project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, time, vote] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") return res.status(405).json({ error: "POST only" });
  const b = req.body || {};
  const id = String(b.id || "").replace(/[^a-z0-9-]/gi, "").slice(0, 32);
  const dir = b.dir === "down" ? -1 : 1;
  if (!id) return res.status(400).json({ error: "id required" });
  try {
    const k = `time:vote:${id}`;
    await q(
      "INSERT INTO mc_state (k, v, updated_at) VALUES ($1, $2, now()) " +
      "ON CONFLICT (k) DO UPDATE SET v = (COALESCE(NULLIF(mc_state.v, '')::int, 0) + $3)::text, updated_at = now()",
      [k, String(dir > 0 ? 1 : 0), dir]);
    const rows = await q("SELECT v FROM mc_state WHERE k=$1", [k]);
    res.status(200).json({ ok: true, votes: Number(rows[0].v) });
  } catch (e) {
    res.status(200).json({ ok: false, note: String(e).slice(0, 120) });
  }
}
