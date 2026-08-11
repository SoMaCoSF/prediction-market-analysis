// file_id: SOM-TS-1005-v1.0.0 name: api/trade/events.js description: Live event feed — aggregates all signal sources from mc_state project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, events, feed, signals, live] created: 2026-08-11 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    const keys = [
      "shadow:latest",
      "xvenue:latest",
      "poly:latest",
      "time:articles",
      "copier:board",
      "uptick:spiral",
      "oracle:current",
      "evidence:lanes",
    ];
    const rows = await q(
      `SELECT k, v, updated_at FROM mc_state WHERE k = ANY($1::text[])`,
      [keys]
    );
    const out = {};
    for (const r of rows) {
      try {
        out[r.k] = JSON.parse(r.v || "[]");
      } catch {
        out[r.k] = r.v;
      }
    }
    const events = [];
    if (Array.isArray(out["shadow:latest"])) {
      for (const s of out["shadow:latest"].slice(0, 8)) {
        events.push({
          ts: s.ts || s.time || "",
          source: "shadow",
          detail: s.detail || s.event || s.symbol || "",
          strength: s.signal01 || s.strength || 0,
        });
      }
    }
    if (Array.isArray(out["xvenue:latest"])) {
      for (const s of out["xvenue:latest"].slice(0, 8)) {
        events.push({
          ts: s.ts || s.time || "",
          source: "xvenue",
          detail: s.detail || s.event || s.ticker || "",
          strength: s.edge_cents || s.strength || 0,
        });
      }
    }
    if (Array.isArray(out["poly:latest"])) {
      for (const s of out["poly:latest"].slice(0, 8)) {
        events.push({
          ts: s.ts || s.time || "",
          source: "polynews",
          detail: s.topic + ": " + (s.title || s.detail || ""),
          strength: s.strength || 0,
        });
      }
    }
    if (Array.isArray(out["copier:board"])) {
      for (const s of out["copier:board"].slice(0, 6)) {
        events.push({
          ts: "",
          source: "copier",
          detail: `whale ${s.wallet?.slice(0,10)||""}… $${s.flow_usd?.toLocaleString()||""}`,
          strength: s.flow_usd || 0,
        });
      }
    }
    events.sort((a, b) => String(b.ts).localeCompare(String(a.ts)));
    res.status(200).json({ events: events.slice(0, 20), ts: Math.floor(Date.now() / 1000) });
  } catch (e) {
    res.status(200).json({ events: [], note: String(e).slice(0, 120) });
  }
}
