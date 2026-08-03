// file_id: SOM-TS-0959-v1.0.0 name: api/trade/tim_bets.js description: Tim bet history — recent live orders with ack/settle status from the ledger project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, tim, bets, history] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    const rows = await q(
      `SELECT o.ticker, o.side, o.price_cents, o.count, o.status, o.ts,
              a.fill_count, a.avg_price_cents
       FROM uuid_orders o
       LEFT JOIN uuid_acks a ON a.parent_uuid = o.uuid
       WHERE o.mode='live'
       ORDER BY o.ts DESC LIMIT 25`);
    res.status(200).json({ bets: rows });
  } catch (e) {
    res.status(200).json({ bets: [], note: String(e).slice(0, 120) });
  }
}
