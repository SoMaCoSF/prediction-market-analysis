// file_id: SOM-TS-0931-v1.0.0 name: api/trade/control.js description: Kill switch + event log endpoints (passkey-gated writes) project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, kill, log, trade] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
import { passkeyOk, isKilled, setKilled, logEvent, recentLog } from "../../../lib/trade-mc";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  const action = req.query.action || (req.method === "GET" ? "log" : "");
  try {
    if (req.method === "GET" && action === "log") {
      return res.status(200).json({ log: await recentLog(120) });
    }
    if (req.method === "POST" && action === "kill") {
      const b = req.body || {};
      if (!passkeyOk(b.passkey)) return res.status(403).json({ error: "bad passkey" });
      const on = Boolean(b.on);
      await setKilled(on);
      await logEvent(on ? "kill" : "warn", on ? "KILL SWITCH ENGAGED — all live firing blocked" : "kill switch disengaged");
      return res.status(200).json({ kill: await isKilled() });
    }
    res.status(400).json({ error: "unknown action" });
  } catch (e) {
    res.status(500).json({ error: String(e).slice(0, 200) });
  }
}
