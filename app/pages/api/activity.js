// file_id: SOM-TS-0912-v1.0.0 name: activity.ts description: Activity endpoint — serves last-known action state (refreshed on deploy) project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, activity, status] created: 2026-07-30 modified: 2026-07-30 version: 1.0.0 agent_id: HERMES-AGENT
/** pages/api/activity.js — serves public/activity.json (our build actions). */
import fs from "fs";
import path from "path";

export default async function handler(req, res) {
  try {
    const p = path.join(process.cwd(), "public", "activity.json");
    const data = JSON.parse(fs.readFileSync(p, "utf-8"));
    res.setHeader("Cache-Control", "no-store");
    res.status(200).json(data);
  } catch (e) {
    res.status(200).json({ phase: "unknown", actions: [], error: String(e.message) });
  }
}
