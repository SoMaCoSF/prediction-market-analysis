// file_id: SOM-TS-0922-v1.0.0 name: lib/trade-db.js description: Supabase PG pool for the trade mission control (shared ledger SoT) project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [db, supabase, ledger, trade] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
/** lib/trade-db.js — pooled PG connection to the Supabase trading ledger.
 *  Env: TRADE_DATABASE_URL or DATABASE_URL or SUPABASE_DB_URL (postgres:// URI).
 *  Native bigint pairs keep the 128-bit bitmask routing intact server-side.
 */
import { Pool } from "pg";

let pool;
export function getPool() {
  if (!pool) {
    const cs = process.env.TRADE_DATABASE_URL || process.env.DATABASE_URL || process.env.SUPABASE_DB_URL;
    if (!cs) throw new Error("TRADE_DATABASE_URL / DATABASE_URL not set");
    pool = new Pool({ connectionString: cs, max: 3, ssl: { rejectUnauthorized: false } });
  }
  return pool;
}

export async function q(text, params) {
  const p = getPool();
  const { rows } = await p.query(text, params);
  return rows;
}
