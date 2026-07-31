import { useState } from "react";

// Passkey derived from OMEN-01 MAC + hostname + salt (same salt the server uses).
// The salt comes from NEXT_PUBLIC_STATUS_SALT (set on Vercel = same value as
// STATUS_SALT). Falls back to the dev default only if unset.
const SALT = process.env.NEXT_PUBLIC_STATUS_SALT || "somacosf-2026";
function derive(mac, host, salt) {
  // minimal SHA-256 in browser via SubtleCrypto
  return crypto.subtle
    .digest("SHA-256", new TextEncoder().encode(`${mac}|${host}|${salt}`))
    .then((b) => [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, "0")).join(""));
}
const MAC = "3024a97f6e32";
const HOST = "omen-01";

export default function Home() {
  const [pass, setPass] = useState("");
  const [unlocked, setUnlocked] = useState(false);
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  async function tryUnlock() {
    const want = await derive(MAC, HOST, SALT);
    if (pass.trim() === want) {
      setUnlocked(true);
      load();
    } else {
      setErr("passkey mismatch");
    }
  }

  async function load() {
    const want = await derive(MAC, HOST, SALT);
    const r = await fetch("/api/status", { headers: { "x-passkey": want } });
    if (!r.ok) {
      setErr("unauthorized from api");
      return;
    }
    setData(await r.json());
  }

  if (!unlocked) {
    return (
      <main style={{ fontFamily: "monospace", background: "#0a0c10", color: "#c8d2dc", minHeight: "100vh", display: "grid", placeItems: "center" }}>
        <div style={{ background: "#10141b", border: "1px solid #1d2630", borderRadius: 8, padding: 28, width: 360 }}>
          <h2 style={{ color: "#06b6d4", marginTop: 0 }}>SoMaCo · UUID Engine</h2>
          <p style={{ color: "#6b7785", fontSize: 12 }}>Enter passkey (derived from OMEN-01 MAC).</p>
          <input value={pass} onChange={(e) => setPass(e.target.value)} placeholder="passkey" style={{ width: "100%", padding: 8, background: "#0c1118", color: "#c8d2dc", border: "1px solid #1d2630", borderRadius: 5 }} />
          <button onClick={tryUnlock} style={{ marginTop: 12, width: "100%", padding: 8, background: "#06b6d4", color: "#03121a", border: 0, borderRadius: 5, cursor: "pointer" }}>Unlock</button>
          {err && <p style={{ color: "#ff5566", fontSize: 12 }}>{err}</p>}
        </div>
      </main>
    );
  }

  return (
    <main style={{ fontFamily: "monospace", background: "#0a0c10", color: "#c8d2dc", padding: 24 }}>
      <h1 style={{ color: "#06b6d4" }}>SoMaCo · Prediction-Market UUID Engine — Status</h1>
      {data ? (
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          <Card label="Trades (uuid_trades)" value={data.trades?.toLocaleString()} />
          <Card label="Wirespeed matched" value={data.wirespeed?.matched?.toLocaleString()} sub={data.wirespeed?.ratio ? `${(data.wirespeed.ratio * 100).toFixed(1)}%` : ""} />
          <Card label="Source" value={data.source} />
          <Card label="Generated" value={data.generated_at} />
        </div>
      ) : (
        <p style={{ color: "#6b7785" }}>loading…</p>
      )}
      {data?.errors?.length ? <p style={{ color: "#ff5566" }}>{data.errors.join("; ")}</p> : null}
      <p style={{ color: "#6b7785", fontSize: 11, marginTop: 24 }}>
        GYST UUIDv8 · markets 0x3A0 (Turso) · trades 0x3A2 (Postgres, bitmask-routable) · wirespeed SQL: {data?.wirespeed?.sql}
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
