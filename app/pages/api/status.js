// file_id: SOM-TS-0911-v1.0.0 name: status.ts description: Public status endpoint (passkey gate removed, shareable) project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, status, public] created: 2026-07-30 modified: 2026-07-30 version: 1.0.0 agent_id: HERMES-AGENT
/** pages/api/status.js — PUBLIC status endpoint (gate removed, shareable). */
import { collectStatus } from "../../lib/status";

export default async function handler(req, res) {
  const status = await collectStatus();
  res.setHeader("Cache-Control", "no-store");
  res.status(200).json(status);
}
