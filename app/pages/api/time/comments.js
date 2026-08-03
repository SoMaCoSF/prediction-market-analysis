// file_id: SOM-TS-0969-v1.0.0 name: api/time/comments.js description: TIME discussion — GET comments for an article, POST a new one (mc_log-backed, kind='time-comment') project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, time, comments, discussion] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    if (req.method === "POST") {
      const b = req.body || {};
      const id = String(b.id || "").replace(/[^a-z0-9]/gi, "").slice(0, 16);
      const name = String(b.name || "anon").slice(0, 24);
      const body = String(b.body || "").slice(0, 500);
      if (!id || !body.trim()) return res.status(400).json({ error: "id + body required" });
      await q("INSERT INTO mc_log (ts, kind, msg) VALUES ($1, 'time-comment', $2)",
              [Math.floor(Date.now() / 1000), `${id}|${name}|${body}`]);
      return res.status(200).json({ ok: true });
    }
    const id = String(req.query.id || "");
    const rows = await q(
      "SELECT ts, msg FROM mc_log WHERE kind='time-comment' AND msg LIKE $1 ORDER BY id DESC LIMIT 40",
      [`${id}|%`]);
    const comments = rows.map((r) => {
      const [, name, ...rest] = r.msg.split("|");
      return { name, body: rest.join("|"), ts: r.ts };
    }).reverse();
    res.status(200).json({ comments });
  } catch (e) {
    res.status(200).json({ comments: [], note: String(e).slice(0, 120) });
  }
}
