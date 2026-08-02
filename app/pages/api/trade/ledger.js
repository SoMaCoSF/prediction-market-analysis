// file_id: SOM-TS-0929-v1.0.0 name: api/trade/ledger.js description: Ledger read views — orders/fills/positions/pnl/acks in one endpoint project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, ledger, trade] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  const view = req.query.view || "orders";
  const limit = Math.min(Number(req.query.limit) || 50, 200);
  try {
    if (view === "orders") {
      const rows = await q(
        `SELECT uuid, client_order_id, ticker, side, price_cents, count, status, mode, exchange_order_id, ts
         FROM uuid_orders ORDER BY created_at DESC LIMIT $1`, [limit]);
      return res.status(200).json({ orders: rows });
    }
    if (view === "fills") {
      const rows = await q(
        `SELECT uuid, parent_uuid, price_cents, count, fee_cents, exchange_fill_id, ts
         FROM uuid_fills ORDER BY created_at DESC LIMIT $1`, [limit]);
      return res.status(200).json({ fills: rows });
    }
    if (view === "acks") {
      const rows = await q(
        `SELECT uuid, parent_uuid, exchange_order_id, fill_count, remaining_count, avg_price_cents, ts
         FROM uuid_acks ORDER BY created_at DESC LIMIT $1`, [limit]);
      return res.status(200).json({ acks: rows });
    }
    if (view === "positions") {
      const rows = await q(
        `SELECT ticker, side, net_count, avg_price_cents, realized_pnl_cents, updated_ts
         FROM uuid_positions ORDER BY ticker, side`);
      return res.status(200).json({ positions: rows });
    }
    if (view === "pnl") {
      const rows = await q("SELECT market_uuid, ticker, orders, filled_contracts, notional_cents, fees_cents FROM uuid_pnl");
      return res.status(200).json({ pnl: rows });
    }
    res.status(400).json({ error: "unknown view" });
  } catch (e) {
    res.status(500).json({ error: String(e).slice(0, 200) });
  }
}
