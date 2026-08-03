// file_id: SOM-TS-0985-v1.0.0 name: api/trade/settles.js description: Settles API — REAL wins/losses from the ledger (uuid_positions realized P&L) project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, settles, realized, ledger] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    const rows = await q(
      "SELECT ticker, side, realized_pnl_cents, updated_ts " +
      "FROM uuid_positions WHERE realized_pnl_cents != 0 " +
      "ORDER BY updated_ts DESC LIMIT 20");
    const tally = await q(
      "SELECT count(*) FILTER (WHERE realized_pnl_cents > 0) AS wins, " +
      "count(*) FILTER (WHERE realized_pnl_cents < 0) AS losses, " +
      "coalesce(sum(realized_pnl_cents), 0) AS total_pnl_cents " +
      "FROM uuid_positions WHERE realized_pnl_cents != 0");
    const t = tally[0] || {};
    res.status(200).json({
      settles: rows.map(r => ({
        ticker: r.ticker,
        side: r.side,
        pnl_cents: Number(r.realized_pnl_cents),
        ts: Number(r.updated_ts),
      })),
      wins: Number(t.wins || 0),
      losses: Number(t.losses || 0),
      total_pnl_cents: Number(t.total_pnl_cents || 0),
    });
  } catch (e) {
    res.status(200).json({ settles: [], wins: 0, losses: 0, total_pnl_cents: 0, note: String(e).slice(0, 120) });
  }
}
