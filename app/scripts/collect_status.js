// scripts/collect_status.js — run at `next build` time.
// Writes app/public/status.json from local (or cloud) Postgres so the deployed
// site has a real snapshot even if Vercel can't reach the LAN DB. The live
// /api/status route still serves fresh data when PG_CONNECTION_STRING is set.
const fs = require("fs");
const path = require("path");

async function main() {
  // lazy require so build doesn't fail if pg isn't installed in CI
  let pg;
  try {
    pg = require("pg");
  } catch (e) {
    console.log("[collect_status] pg not available, skipping");
    return;
  }
  const cs = process.env.PG_CONNECTION_STRING;
  const pool = new pg.Pool(
    cs
      ? { connectionString: cs }
      : {
          host: process.env.PGHOST || "127.0.0.1",
          port: Number(process.env.PGPORT || 5432),
          database: process.env.PGDATABASE || "postgres",
          user: process.env.PGUSER || "postgres",
          password: process.env.PGPASSWORD || "hermes_pg_2026",
        }
  );
  try {
    const t = await pool.query("SELECT count(*)::bigint AS n FROM uuid_trades");
    const w = await pool.query(
      "SELECT count(*)::bigint AS m FROM uuid_trades WHERE ((uuid_hi >> 52) & 4095) = 930"
    );
    const out = {
      generated_at: new Date().toISOString(),
      source: cs ? "cloud-postgres" : "local-postgres",
      trades: Number(t.rows[0].n),
      wirespeed: { sql: "((uuid_hi >> 52) & 4095) = 0x3A2", matched: Number(w.rows[0].m) },
    };
    const pub = path.join(__dirname, "..", "public");
    fs.mkdirSync(pub, { recursive: true });
    fs.writeFileSync(path.join(pub, "status.json"), JSON.stringify(out, null, 2));
    console.log("[collect_status] wrote", pub + "/status.json", out);
  } catch (e) {
    console.log("[collect_status] error:", e.message);
  } finally {
    await pool.end();
  }
}
main();
