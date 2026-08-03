// file_id: SOM-TS-0960-v1.0.0 name: api/trade/autofollow.js description: Auto-follow super-trends toggle — GET state, POST set (mc_state autofollow:trend) project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, autofollow, toggle] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    if (req.method === "POST") {
      const on = !!(req.body && req.body.on);
      await q(
        "INSERT INTO mc_state (k, v, updated_at) VALUES ('autofollow:trend', $1, now()) " +
        "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
        [on ? "on" : "off"]);
      return res.status(200).json({ ok: true, on });
    }
    const rows = await q("SELECT v FROM mc_state WHERE k='autofollow:trend'");
    res.status(200).json({ on: rows.length && rows[0].v === "on" });
  } catch (e) {
    res.status(200).json({ on: false, note: String(e).slice(0, 120) });
  }
}
