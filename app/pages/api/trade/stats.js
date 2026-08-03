// file_id: SOM-TS-0927-v1.0.0 name: api/trade/stats.js description: Mission control stats — ledger counts, P&L, kill, keys (Supabase) project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, stats, trade] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";
import { isKilled } from "../../../lib/trade-mc";
import { keysPresent } from "../../../lib/trade-kalshi";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    const [orders] = await q("SELECT count(*)::int c FROM uuid_orders");
    const [fills] = await q("SELECT count(*)::int c FROM uuid_fills");
    const [pnl] = await q("SELECT coalesce(sum(realized_pnl_cents),0)::bigint r FROM uuid_positions");
    const [exp] = await q("SELECT coalesce(sum(net_count),0)::bigint e FROM uuid_positions");
    let account = null;
    try {
      const acct = await q("SELECT v FROM mc_state WHERE k='account:equity'");
      if (acct.length) account = JSON.parse(acct[0].v);
    } catch { /* mc_state optional */ }
    res.status(200).json({
      corpus: { online: null, note: "corpus is local-PG; cloud shows ledger only" },
      ledger: { orders: orders.c, fills: fills.c, realized_pnl_cents: Number(pnl.r), open_contracts: Number(exp.e) },
      account,
      kill: await isKilled(),
      keys: keysPresent(),
      ts: Math.floor(Date.now() / 1000),
    });
  } catch (e) {
    res.status(500).json({ error: String(e).slice(0, 200) });
  }
}
