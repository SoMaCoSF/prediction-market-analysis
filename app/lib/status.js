/** lib/status.js — collects UUID-engine status.
 *  Today: reads LOCAL Postgres (127.0.0.1). Cloud-ready: set PG_CONNECTION_STRING
 *  to a hosted Postgres (Supabase/Neon) and it reads live from there instead.
 */
import { Pool } from "pg";

let _pool = null;
function pool() {
  if (_pool) return _pool;
  const cs = process.env.PG_CONNECTION_STRING;
  _pool = new Pool(cs ? { connectionString: cs } : {
    host: process.env.PGHOST || "127.0.0.1",
    port: Number(process.env.PGPORT || 5432),
    database: process.env.PGDATABASE || "postgres",
    user: process.env.PGUSER || "postgres",
    password: process.env.PGPASSWORD || "hermes_pg_2026",
  });
  return _pool;
}

export async function collectStatus() {
  const out = {
    generated_at: new Date().toISOString(),
    source: process.env.PG_CONNECTION_STRING ? "cloud-postgres" : "local-postgres",
    trades: null,
    markets_turso: null,
    wirespeed: null,
    errors: [],
  };
  try {
    const p = pool();
    const t = await p.query("SELECT count(*)::bigint AS n FROM uuid_trades");
    out.trades = Number(t.rows[0].n);

    // wirespeed bitmask proof: ((uuid_hi >> 52) & 4095) = 0x3A2
    const w = await p.query(
      "SELECT count(*)::bigint AS m FROM uuid_trades WHERE ((uuid_hi >> 52) & 4095) = 930"
    );
    out.wirespeed = {
      sql: "((uuid_hi >> 52) & 4095) = 0x3A2",
      matched: Number(w.rows[0].m),
      ratio: out.trades ? Number(w.rows[0].m) / out.trades : 0,
    };
  } catch (e) {
    out.errors.push(String(e.message || e));
  }
  return out;
}
