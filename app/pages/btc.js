import { useEffect, useState } from "react";

export default function BtcPaper() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    fetch("/api/btc/summary")
      .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
      .then(setData)
      .catch(e => setErr(String(e)));
  }, []);

  return (
    <main style={{ fontFamily: "monospace", background: "#0a0c10", color: "#c8d2dc", padding: 24, minHeight: "100vh" }}>
      <h1 style={{ color: "#06b6d4" }}>SoMaCo · BTC Short Paper Test</h1>
      <p style={{ color: "#6b7785", fontSize: 12 }}>Paper only · no live capital · short-only thesis</p>

      {err && <p style={{ color: "#ff5555", fontSize: 12, marginTop: 8 }}>error: {err}</p>}

      {data && (
        <>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 12 }}>
            <Card label="BTC Spot" value={data.spot ? `$${data.spot.toLocaleString()}` : "—"} />
            <Card label="Open Paper Positions" value={data.summary?.open ?? 0} />
            <Card label="Closed Trades" value={data.summary?.closed ?? 0} />
            <Card label="Paper P&L" value={`${data.summary?.pnl_cents ?? 0}¢`} sub={data.summary?.pnl_cents >= 0 ? "profit" : "loss"} />
          </div>

          <h2 style={{ color: "#39ff14", marginTop: 28, fontSize: 14, textTransform: "uppercase", letterSpacing: 1.5 }}>Paper Positions</h2>
          <div style={{ background: "#10141b", border: "1px solid #1d2630", borderRadius: 8, padding: 16, maxWidth: 900 }}>
            {(!data.paper_trades || data.paper_trades.length === 0) && (
              <p style={{ color: "#6b7785", fontSize: 12 }}>no paper trades yet</p>
            )}
            {data.paper_trades?.map((t, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px dashed #161c25", fontSize: 12 }}>
                <span>{t.ticker}</span>
                <span>short @ {t.entry_price?.toLocaleString()}c</span>
                <span>notional {t.notional_cents?.toLocaleString()}c</span>
                <span style={{ color: t.status === "open" ? "#ffaa55" : t.pnl_cents >= 0 ? "#39ff14" : "#ff5555" }}>
                  {t.status === "open" ? "OPEN" : `${t.pnl_cents >= 0 ? "+" : ""}${t.pnl_cents}c`}
                </span>
              </div>
            ))}
          </div>

          <p style={{ color: "#6b7785", fontSize: 11, marginTop: 24 }}>
            Source: live BTC spot feed · paper positions from public/btc_paper_trades.json · short-only
          </p>
        </>
      )}
    </main>
  );
}

function Card({ label, value, sub }) {
  return (
    <div style={{ background: "#10141b", border: "1px solid #1d2630", borderRadius: 8, padding: 16, minWidth: 180 }}>
      <div style={{ color: "#6b7785", fontSize: 11, textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: 22, color: "#39ff14", marginTop: 6 }}>{value ?? "—"}</div>
      {sub && <div style={{ color: "#06b6d4", fontSize: 12 }}>{sub}</div>}
    </div>
  );
}
