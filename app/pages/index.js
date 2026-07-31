import { useState, useEffect } from "react";

// uuid.somacosf.com — PUBLIC status + activity surface for the GYST UUID engine.
// No passkey gate (shareable). Shows live engine state + our build actions.
// Activity is served from /api/activity (last-known action state, refreshed on deploy).

export default function Home() {
  const [status, setStatus] = useState(null);
  const [activity, setActivity] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    fetch("/api/status").then(r => r.ok ? r.json() : null).then(setStatus).catch(() => {});
    fetch("/api/activity").then(r => r.ok ? r.json() : null).then(setActivity).catch(() => {});
  }, []);

  return (
    <main style={{ fontFamily: "monospace", background: "#0a0c10", color: "#c8d2dc", padding: 24, minHeight: "100vh" }}>
      <h1 style={{ color: "#06b6d4" }}>SoMaCo · Prediction-Market UUID Engine — Status</h1>
      <p style={{ color: "#6b7785", fontSize: 12 }}>Public surface · GYST UUIDv8 · source of truth = local Postgres (OMEN-01) · cloud slice = Supabase</p>

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 12 }}>
        <Card label="Trades (uuid_trades)" value={status?.trades?.toLocaleString()} sub={status?.source} />
        <Card label="Wirespeed matched" value={status?.wirespeed?.matched?.toLocaleString()}
              sub={status?.wirespeed?.ratio ? `${(status.wirespeed.ratio * 100).toFixed(1)}%` : ""} />
        <Card label="Generated" value={status?.generated_at} />
      </div>

      {status?.errors?.length ? (
        <p style={{ color: "#ffaa55", fontSize: 12, marginTop: 8 }}>
          note: live DB unreachable from Vercel (Supabase free-tier DNS) — showing build snapshot. {status.errors.join("; ")}
        </p>
      ) : null}

      <h2 style={{ color: "#39ff14", marginTop: 28, fontSize: 14, textTransform: "uppercase", letterSpacing: 1.5 }}>Our Actions</h2>
      {activity ? (
        <div style={{ background: "#10141b", border: "1px solid #1d2630", borderRadius: 8, padding: 16, maxWidth: 640 }}>
          <div style={{ color: "#6b7785", fontSize: 11, marginBottom: 8 }}>phase: {activity.phase} · updated {activity.updated_at}</div>
          {activity.actions?.map((a, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px dashed #161c25" }}>
              <span style={{ color: "#c8d2dc" }}>{a.label}</span>
              <span style={{ color: a.status === "done" ? "#39ff14" : a.status === "running" ? "#ffaa55" : "#6b7785", fontSize: 11 }}>
                {a.status === "running" ? "● running" : a.status === "done" ? "✓ done" : a.status}
              </span>
            </div>
          ))}
          <div style={{ color: "#6b7785", fontSize: 11, marginTop: 10 }}>
            A (flat): {activity.source_of_truth?.A_flat_table}<br />
            B (spawn): {activity.source_of_truth?.B_spawn_tables}
          </div>
          <div style={{ color: "#6b7785", fontSize: 11, marginTop: 6 }}>compliance: {activity.compliance}</div>
        </div>
      ) : <p style={{ color: "#6b7785" }}>loading actions…</p>}

      <p style={{ color: "#6b7785", fontSize: 11, marginTop: 24 }}>
        GYST UUIDv8 · markets 0x3A0 (Turso) · trades 0x3A2 (Postgres, bitmask-routable) · quotes 0x3A1 ·
        wirespeed SQL: {status?.wirespeed?.sql || "((uuid_hi >> 52) & 4095) = 0x3A2"}
      </p>
    </main>
  );
}

function Card({ label, value, sub }) {
  return (
    <div style={{ background: "#10141b", border: "1px solid #1d2630", borderRadius: 8, padding: 16, minWidth: 200 }}>
      <div style={{ color: "#6b7785", fontSize: 11, textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: 22, color: "#39ff14", marginTop: 6 }}>{value ?? "—"}</div>
      {sub && <div style={{ color: "#06b6d4", fontSize: 12 }}>{sub}</div>}
    </div>
  );
}
