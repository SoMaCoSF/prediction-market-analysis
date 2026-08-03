// file_id: SOM-TS-0971-v1.0.0 name: api/trade/positions.js description: Positions API — open positions + realized from the ledger (uuid_positions) project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, positions, ledger] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    const rows = await q(
      "SELECT ticker, side, net_count, avg_price_cents, realized_pnl_cents " +
      "FROM uuid_positions WHERE net_count != 0 OR realized_pnl_cents != 0 " +
      "ORDER BY abs(net_count) DESC LIMIT 60");
    res.status(200).json({ positions: rows });
  } catch (e) {
    res.status(200).json({ positions: [], note: String(e).slice(0, 120) });
  }
}
