// file_id: SOM-TS-0980-v1.0.0 name: api/trade/equity.js description: Equity history API — the account curve (equity_history written by fill_poller) project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, equity, history, curve] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    const rows = await q(
      "SELECT ts, equity, cash, portfolio FROM equity_history ORDER BY ts DESC LIMIT 240");
    res.status(200).json({ history: rows.reverse() });
  } catch (e) {
    res.status(200).json({ history: [], note: String(e).slice(0, 120) });
  }
}
