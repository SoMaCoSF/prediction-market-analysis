// file_id: SOM-TS-0973-v1.0.0 name: api/trade/lanes.js description: Lanes API — fleet health + per-lane open/realized decomposition for the dashboard project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, lanes, fleet, pnl] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

const LANE_OF = (t) =>
  t.includes("15M") ? "momentum-15M" :
  t.includes("KXMV") ? "parlay-tails" :
  /^KX(MLB|NBA|NFL|ATP|WTA|ITF)/.test(t) ? "sports" :
  /^KX(WTI|NASDAQ|SP500|WHEAT)/.test(t) ? "news" : "other";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    const daemons = await q("SELECT k, v, updated_at FROM mc_state WHERE k LIKE 'daemon:%'");
    const now = Date.now();
    const fleet = daemons.map((r) => ({
      name: r.k.replace("daemon:", ""), state: r.v,
      age_s: Math.max(0, Math.round((now - new Date(r.updated_at).getTime()) / 1000)),
    }));
    const rows = await q(
      "SELECT ticker, net_count, avg_price_cents, realized_pnl_cents FROM uuid_positions WHERE net_count != 0 OR realized_pnl_cents != 0");
    const lanes = {};
    for (const r of rows) {
      const l = LANE_OF(r.ticker || "");
      lanes[l] = lanes[l] || { open: 0, cost_usd: 0, realized_usd: 0 };
      lanes[l].open += Number(r.net_count) || 0;
      lanes[l].cost_usd += (Number(r.net_count) || 0) * (Number(r.avg_price_cents) || 0) / 100;
      lanes[l].realized_usd += (Number(r.realized_pnl_cents) || 0) / 100;
    }
    const sp = await q("SELECT v FROM mc_state WHERE k='sweep:pending'");
    const ss = await q("SELECT v FROM mc_state WHERE k='sweep:stats'");
    res.status(200).json({
      fleet, lanes,
      sweep_pending: sp.length && sp[0].v ? JSON.parse(sp[0].v) : null,
      sweep_stats: ss.length && ss[0].v ? JSON.parse(ss[0].v) : null,
    });
  } catch (e) {
    res.status(200).json({ fleet: [], lanes: {}, note: String(e).slice(0, 120) });
  }
}
