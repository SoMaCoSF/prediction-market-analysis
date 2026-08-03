// file_id: SOM-TS-0946-v1.0.0 name: api/trade/dry.js description: Dry-run state API — paper engine state from mc_state + recent dry events from mc_log project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, dry-run, paper] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  try {
    const st = await q("SELECT v, updated_at FROM mc_state WHERE k='dry_run_state'");
    const ev = await q("SELECT ts, msg FROM mc_log WHERE kind='dry' ORDER BY id DESC LIMIT 60");
    let state = null;
    if (st.length) {
      try { state = JSON.parse(st[0].v); } catch { state = { raw: st[0].v }; }
      state.state_updated_at = st[0].updated_at;
    }
    res.status(200).json({ state, events: ev.reverse() });
  } catch (e) {
    res.status(200).json({ state: null, events: [], note: `dry feed unavailable: ${String(e).slice(0, 120)}` });
  }
}
