// file_id: SOM-TS-0996-v1.0.0 name: api/time/status.js description: Agent status API — hermes:status (what the agent is doing, fleet, equity, commit) + governor state project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, status, agent, transparency] created: 2026-08-04 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    const rows = await q("SELECT k, v, EXTRACT(EPOCH FROM (now()-updated_at)) AS age_s FROM mc_state WHERE k IN ('hermes:status','governor:state','evidence:lanes','xvenue:latest')");
    const out = {};
    for (const r of rows) {
      try { out[r.k.replace(":", "_")] = { ...JSON.parse(r.v), age_s: Math.round(Number(r.age_s)) }; }
      catch { out[r.k.replace(":", "_")] = { raw: r.v }; }
    }
    // MICRO CALC — the grind math, both venues
    const today = await q(
      "SELECT count(*) AS entries, avg(price_cents) AS avg_px FROM uuid_orders WHERE mode='live' AND ts > EXTRACT(EPOCH FROM date_trunc('day', now()))");
    const realized = await q(
      "SELECT count(*) AS n, count(*) FILTER (WHERE realized_pnl_cents > 0) AS wins, sum(realized_pnl_cents) AS total FROM uuid_positions WHERE realized_pnl_cents != 0");
    const n = Number(realized[0].n) || 0, w = Number(realized[0].wins) || 0;
    out.micro = {
      kalshi: {
        entries_today: Number(today[0].entries) || 0,
        avg_entry_c: Math.round(Number(today[0].avg_px) || 0),
        settled: n, wins: w, win_rate: n ? Math.round(100 * w / n) : 0,
        realized_usd: (Number(realized[0].total) || 0) / 100,
        expectancy_c: n ? Math.round((Number(realized[0].total) || 0) / n) : 0,
      },
      poly: {
        divergences: Array.isArray(out.xvenue_latest) ? out.xvenue_latest.length : 0,
        note: "signal venue — executions settle on Kalshi",
      },
    };
    res.status(200).json(out);
  } catch (e) {
    res.status(200).json({ error: String(e).slice(0, 200) });
  }
}