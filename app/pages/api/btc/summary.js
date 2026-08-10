// file_id: SOM-TS-XXXX-v1.0.0 name: btc/summary.js description: BTC paper-test summary API
/** pages/api/btc/summary.js — BTC short paper-test summary. */
export default async function handler(req, res) {
  try {
    const fs = require("fs");
    const path = require("path");
    const statePath = path.join(process.cwd(), "..", "data", "btc_paper_state.json");
    const tradesPath = path.join(process.cwd(), "..", "app", "public", "btc_paper_trades.json");
    const state = fs.existsSync(statePath) ? JSON.parse(fs.readFileSync(statePath, "utf-8")) : {};
    const trades = fs.existsSync(tradesPath) ? JSON.parse(fs.readFileSync(tradesPath, "utf-8")) : [];
    res.setHeader("Cache-Control", "no-store");
    res.status(200).json({
      generated_at: state.generated_at || new Date().toISOString(),
      spot: state.last_spot || null,
      paper_trades: trades,
      summary: {
        open: trades.filter(t => t.status === "open").length,
        closed: trades.filter(t => t.status === "closed").length,
        pnl_usd: Number((state.session_pnl_usd || 0).toFixed(2)),
      },
    });
  } catch (e) {
    res.status(200).json({ generated_at: new Date().toISOString(), error: String(e.message || e), paper_trades: [], summary: { open: 0, closed: 0, pnl_cents: 0 } });
  }
}
