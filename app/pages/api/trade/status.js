// file_id: SOM-TS-0988-v1.0.0 name: api/trade/status.js description: Status API — the real-time logic proof: LIVE vs PAPER split, pipeline chain freshness, fleet, computed PASS/FAIL checks project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, status, proof, live-vs-paper, checks] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

const age = (t) => Math.max(0, Math.round(Date.now() / 1000 - Number(t || 0)));

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  const out = { checks: [] };
  try {
    // 1. LIVE vs PAPER — the money truth
    const modes = await q("SELECT mode, count(*) AS n FROM uuid_orders GROUP BY mode");
    out.orders_by_mode = Object.fromEntries(modes.map((r) => [r.mode, Number(r.n)]));
    const liveFills = await q("SELECT count(*) AS n, max(ts) AS last_ts FROM uuid_fills");
    out.fills = { total: Number(liveFills[0].n), last_age_s: age(liveFills[0].last_ts) };
    const lastOrder = await q(
      "SELECT ticker, side, price_cents, count, mode, status, exchange_order_id, ts FROM uuid_orders WHERE mode='live' ORDER BY ts DESC LIMIT 1");
    out.last_order = lastOrder[0] || null;
    const lastSettle = await q(
      "SELECT ticker, realized_pnl_cents FROM uuid_positions WHERE realized_pnl_cents != 0 ORDER BY ticker DESC LIMIT 5");
    out.recent_realized = lastSettle;

    // 2. pipeline freshness (mc_state)
    const st = await q("SELECT k, v, updated_at, EXTRACT(EPOCH FROM (now()-updated_at)) AS age_s FROM mc_state WHERE k IN ('account:equity','tick:health','evidence:lanes','sweep:pending')");
    out.state = {};
    for (const r of st) out.state[r.k] = { age_s: Math.round(Number(r.age_s)), v: r.k === "tick:health" ? JSON.parse(r.v) : undefined };

    // 3. fleet
    const daemons = await q("SELECT k, v, EXTRACT(EPOCH FROM (now()-updated_at)) AS age_s FROM mc_state WHERE k LIKE 'daemon:%'");
    out.fleet = daemons.map((r) => ({ name: r.k.replace("daemon:", ""), state: r.v, age_s: Math.round(Number(r.age_s)) }));
    const fleetLive = out.fleet.filter((d) => d.state === "alive" && d.age_s < 400).length;

    // 4. computed checks — the page's own PASS/FAIL
    const acctAge = out.state["account:equity"] ? out.state["account:equity"].age_s : 99999;
    const tickSyms = out.state["tick:health"] && out.state["tick:health"].v ? Object.keys(out.state["tick:health"].v.symbols || {}).length : 0;
    out.checks = [
      { name: "LIVE orders exist (mode=live)", pass: (out.orders_by_mode.live || 0) > 0, detail: `${out.orders_by_mode.live || 0} live / ${out.orders_by_mode.paper || 0} paper` },
      { name: "fills flowing", pass: out.fills.last_age_s < 600, detail: `last fill ${out.fills.last_age_s}s ago (${out.fills.total} total)` },
      { name: "account feed fresh", pass: acctAge < 300, detail: `${acctAge}s old` },
      { name: "tick plane streaming", pass: tickSyms >= 3, detail: `${tickSyms} symbols` },
      { name: "fleet alive", pass: fleetLive >= 15, detail: `${fleetLive}/${out.fleet.length} lanes` },
      { name: "last live order acked", pass: !!(out.last_order && out.last_order.exchange_order_id), detail: out.last_order ? `${out.last_order.ticker} ${out.last_order.status}` : "none" },
    ];
  } catch (e) {
    out.error = String(e).slice(0, 200);
  }
  res.status(200).json(out);
}
