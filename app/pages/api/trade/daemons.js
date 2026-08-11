// file_id: SOM-TS-0999-v1.0.0 name: api/trade/daemons.js description: Rich daemon beats — heartbeat age, what each watches, uptime, last action from mc_state + heartbeat files project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, daemons, fleet, beats, heartbeat] created: 2026-08-11 version: 1.0.0 agent_id: HERMES-AGENT
// API: /api/trade/daemons — returns per-daemon live beats with role descriptions and heartbeat freshness
import { q } from "../../../lib/trade-db";

// What each daemon watches and why
const DAEMON_ROLES = {
  mc: { watches: "Mission control — order routing, kill switch, floor guard", category: "core" },
  vault: { watches: "Key vault — API key presence, Kalshi auth state", category: "core" },
  scalp: { watches: "Profit-scalp — mean-reversion entries on 15M crypto", category: "trading" },
  btctrend: { watches: "BTC trend engine — directional momentum on Bitcoin", category: "trading" },
  trend_eth: { watches: "ETH trend engine — directional momentum on Ethereum", category: "trading", alias: "trend-eth" },
  trend_sol: { watches: "SOL trend engine — directional momentum on Solana", category: "trading", alias: "trend-sol" },
  trend_xrp: { watches: "XRP trend engine — directional momentum on Ripple", category: "trading", alias: "trend-xrp" },
  trend_doge: { watches: "DOGE trend engine — directional momentum on Dogecoin", category: "trading", alias: "trend-doge" },
  xwatch: { watches: "X/Twitter signal scanner — sentiment + breaking news", category: "signal" },
  shadow: { watches: "Shadow index — whale wallet tracking (not our money)", category: "signal" },
  maker: { watches: "Maker engine — passive limit order placement", category: "trading" },
  sweep: { watches: "Sweep watch — cash threshold alerts (Venmo withdrawal trigger)", category: "ops" },
  news: { watches: "News supply engine — RSS/news ingestion for event signals", category: "signal" },
  dry: { watches: "Paper engine — dry-run trades for proof without capital", category: "paper" },
  dry_t10: { watches: "Paper 10s cycle — fast dry-run loop", category: "paper", alias: "dry-t10" },
  dry_t20: { watches: "Paper 20s cycle — medium dry-run loop", category: "paper", alias: "dry-t20" },
  dry_t25: { watches: "Paper 25s cycle — slow dry-run loop", category: "paper", alias: "dry-t25" },
  dry_s15_8: { watches: "Paper $1.50 x8 cycle — micro-stake dry-run", category: "paper", alias: "dry-s15-8" },
  copier: { watches: "Whale copier — mirrors large market movements", category: "signal" },
  ws: { watches: "Kalshi WebSocket — live tick/fill stream", category: "core" },
  tick: { watches: "Tick service — normalized price feed for all symbols", category: "core" },
  xvenue: { watches: "Cross-venue engine — Kalshi vs Polymarket arb scanner", category: "trading" },
  calendar: { watches: "Calendar engine — scheduled event outcomes (settlements)", category: "ops" },
  promoter: { watches: "Promoter — position promotion/rebalance logic", category: "trading" },
  governor: { watches: "Governor — risk limits, position sizing enforcement", category: "core" },
  agent_status: { watches: "Agent status — fleet health aggregator", category: "ops", alias: "agent-status" },
  oracle: { watches: "Oracle — settlement truth verification", category: "core" },
  poly_exec: { watches: "Polymarket executor — on-chain order placement (dormant until funded)", category: "trading", alias: "poly-exec" },
  funding: { watches: "Funding feed — watches wallet for inbound USDC deposits", category: "ops" },
  bridge: { watches: "Bridge coordinator — cross-venue state sync", category: "core" },
  evidence: { watches: "Evidence engine — statistical edge validation per lane", category: "ops" },
  ingest: { watches: "Ingest — batch data pipeline (trades, fills, markets)", category: "core" },
  recover: { watches: "Recovery engine — crash capture + auto-restart daemons", category: "ops" },
  chaos: { watches: "Chaos monkey — randomized stress testing (inactive)", category: "ops" },
  moonshot: { watches: "Moonshot sleeve — high-risk high-reward parlay lane", category: "trading" },
  parlay: { watches: "Parlay tails — multi-game composite bets", category: "trading" },
  speed_btc: { watches: "Speed BTC — high-frequency BTC micro-scalper", category: "trading", alias: "speed-btc" },
  speed_eth: { watches: "Speed ETH — high-frequency ETH micro-scalper", category: "trading", alias: "speed-eth" },
  fills: { watches: "Fill poller — exchange-truth fill verification", category: "core" },
  uptick: { watches: "Uptick spiral — forecast accuracy scoring (Brier score)", category: "signal" },
};

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  const out = { daemons: [], ts: Math.round(Date.now() / 1000) };
  try {
    const rows = await q(
      "SELECT k, v, updated_at, EXTRACT(EPOCH FROM (now()-updated_at)) AS age_s FROM mc_state WHERE k LIKE 'daemon:%' ORDER BY k"
    );
    for (const r of rows) {
      const name = r.k.replace("daemon:", "");
      const state = r.v;
      const ageS = Math.round(Number(r.age_s));
      const isLive = state === "alive" && ageS < 400;
      const role = DAEMON_ROLES[name] || DAEMON_ROLES[name.replace(/-/g, "_")] || { watches: "unknown", category: "other" };
      out.daemons.push({
        name,
        state,
        age_s: ageS,
        live: isLive,
        watches: role.watches,
        category: role.category,
        last_beat: r.updated_at,
      });
    }
    // Summary counts
    const byCategory = {};
    for (const d of out.daemons) {
      byCategory[d.category] = byCategory[d.category] || { total: 0, live: 0 };
      byCategory[d.category].total++;
      if (d.live) byCategory[d.category].live++;
    }
    out.summary = {
      total: out.daemons.length,
      live: out.daemons.filter((d) => d.live).length,
      by_category: byCategory,
    };
  } catch (e) {
    out.error = String(e).slice(0, 200);
  }
  res.status(200).json(out);
}
