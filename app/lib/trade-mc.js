// file_id: SOM-TS-0926-v1.0.0 name: lib/trade-mc.js description: Shared mission-control helpers — passkey check, kill state + event log in Supabase (serverless-safe) project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [passkey, kill-switch, log, trade] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
/** lib/trade-mc.js — serverless-safe control state.
 *  Kill switch + event log live in Supabase (no shared memory on Vercel).
 *  Passkey = same derivation as lib/auth.js and the local Python MC.
 */
import { checkPasskey } from "./auth";
import { q } from "./trade-db";

export function passkeyOk(candidate) {
  return checkPasskey(candidate || "");
}

export async function isKilled() {
  const rows = await q("SELECT v FROM mc_state WHERE k='kill'").catch(() => []);
  return rows.length > 0 && rows[0].v === "1";
}

export async function setKilled(on) {
  if (on) {
    await q("INSERT INTO mc_state (k, v) VALUES ('kill','1') ON CONFLICT (k) DO UPDATE SET v='1', updated_at=now()");
  } else {
    await q("INSERT INTO mc_state (k, v) VALUES ('kill','0') ON CONFLICT (k) DO UPDATE SET v='0', updated_at=now()");
  }
}

export async function logEvent(kind, msg) {
  await q("INSERT INTO mc_log (ts, kind, msg) VALUES ($1,$2,$3)", [Math.floor(Date.now() / 1000), kind, String(msg).slice(0, 400)])
    .catch(() => {});
}

export async function recentLog(limit = 120) {
  return q("SELECT ts, kind, msg FROM mc_log ORDER BY id DESC LIMIT $1", [limit]).catch(() => []);
}
