// file_id: SOM-TS-0991-v1.0.0 name: api/trade/funds.js description: FUNDS API — the money truth across both venues: equity/cash/marks/realized, per-lane returns, vault, moonshot sleeve, sweep state, Polymarket signal flow project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, funds, returns, pnl, venues] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  const out = {};
  try {
    const st = await q("SELECT k, v, updated_at, EXTRACT(EPOCH FROM (now()-updated_at)) AS age_s FROM mc_state WHERE k IN ('account:equity','vault:state','moonshot:sleeve','sweep:stats','sweep:pending','evidence:lanes','xvenue:latest','copier:board')");
    for (const r of st) {
      try { out[r.k.replace(":", "_")] = { ...JSON.parse(r.v), age_s: Math.round(Number(r.age_s)) }; }
      catch { out[r.k.replace(":", "_")] = { raw: r.v, age_s: Math.round(Number(r.age_s)) }; }
    }
    const modes = await q("SELECT mode, count(*) AS n FROM uuid_orders GROUP BY mode");
    out.orders_by_mode = Object.fromEntries(modes.map((r) => [r.mode, Number(r.n)]));
    const rl = await q("SELECT count(*) AS n, count(*) FILTER (WHERE realized_pnl_cents > 0) AS wins, sum(realized_pnl_cents) AS total FROM uuid_positions WHERE realized_pnl_cents != 0");
    out.realized = { n: Number(rl[0].n), wins: Number(rl[0].wins), total_usd: Number(rl[0].total || 0) / 100 };
    const lanes = await q("SELECT ticker, net_count, avg_price_cents, realized_pnl_cents FROM uuid_positions WHERE net_count != 0 OR realized_pnl_cents != 0");
    const LANE_OF = (t) => t.includes("15M") ? "momentum-15M" : t.includes("KXMV") ? "parlay-tails" : /^KX(MLB|NBA|NFL|ATP|WTA|ITF)/.test(t) ? "sports" : /^KX(WTI|CPI)/.test(t) ? "supply-chain" : "other";
    const agg = {};
    for (const r of lanes) {
      const l = LANE_OF(r.ticker || "");
      agg[l] = agg[l] || { open: 0, cost_usd: 0, realized_usd: 0 };
      agg[l].open += Number(r.net_count) || 0;
      agg[l].cost_usd += (Number(r.net_count) || 0) * (Number(r.avg_price_cents) || 0) / 100;
      agg[l].realized_usd += (Number(r.realized_pnl_cents) || 0) / 100;
    }
    out.lanes = agg;
    const curve = await q("SELECT ts, equity FROM equity_history ORDER BY ts DESC LIMIT 200");
    out.curve = curve.reverse().map((r) => ({ ts: r.ts, equity: Number(r.equity) }));
  } catch (e) {
    out.error = String(e).slice(0, 200);
  }
  res.status(200).json(out);
}
