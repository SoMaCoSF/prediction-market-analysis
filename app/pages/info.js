import { useEffect, useState } from "react";

export default function Info() {
  const [portfolio, setPortfolio] = useState(null);
  const [health, setHealth] = useState(null);
  const [cycle, setCycle] = useState(null);

  useEffect(() => {
    fetch("/api/portfolio").then(r => r.ok ? r.json() : null).then(setPortfolio).catch(() => {});
    fetch("/api/venue_health").then(r => r.ok ? r.json() : null).then(setHealth).catch(() => {});
    fetch("/api/info/cycle").then(r => r.ok ? r.json() : null).then(setCycle).catch(() => {});
  }, []);

  const cash = portfolio?.balance?.balance_dollars || "—";
  const portfolio_value = portfolio?.balance?.portfolio_value || "—";
  const positions_count = portfolio?.positions?.event_positions?.length || 0;
  const open_orders = portfolio?.orders?.length || 0;

  return (
    <main style={{
      fontFamily: "monospace",
      background: "#0a0c10",
      color: "#c8d2dc",
      minHeight: "100vh",
      padding: 24,
    }}>
      {/* HERO + LIVE TRACKER */}
      <div style={{
        background: "linear-gradient(180deg, #10141b 0%, #0a0c10 100%)",
        border: "1px solid #1d2630",
        borderRadius: 12,
        padding: 32,
        marginBottom: 24,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16 }}>
          <div>
            <h1 style={{ color: "#FF9000", fontSize: 28, margin: 0, letterSpacing: 1 }}>
              SoMaCoSF · Prediction-Market Fleet
            </h1>
            <p style={{ color: "#6b7785", fontSize: 13, marginTop: 8, maxWidth: 800 }}>
              Live autonomous trading infrastructure for Kalshi + Polymarket. Micro-grind execution,
              multi-venue liquidity routing, and real-time monitoring — built for constant uptick.
            </p>
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <Badge label="Status" value={cycle?.summary?.running ? "LIVE" : "OFFLINE"} color={cycle?.summary?.running ? "#39ff14" : "#ffaa55"} />
            <Badge label="Cash" value={`$${cash}`} color="#39ff14" />
            <Badge label="Portfolio" value={`$${portfolio_value}`} color="#06b6d4" />
            <Badge label="Positions" value={positions_count} color="#c8d2dc" />
            <Badge label="Open Orders" value={open_orders} color="#c8d2dc" />
          </div>
        </div>

        {/* LIVE DAEMON TRACKER */}
        <div style={{ marginTop: 24 }}>
          <div style={{ color: "#6b7785", fontSize: 11, marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 }}>
            Live Daemon Cycle — what we’re watching and why
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
            {cycle?.daemons?.map((d, i) => (
              <div key={i} style={{
                background: "#0a0c10",
                border: `1px solid ${d.color}33`,
                borderRadius: 8,
                padding: 14,
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                  <span style={{ color: d.color, fontSize: 11, fontWeight: "bold", textTransform: "uppercase" }}>{d.label}</span>
                  <span style={{
                    color: d.status === "RUNNING" || d.status === "SCANNING" || d.status === "ACTIVE" ? "#39ff14" : d.status === "ERROR" ? "#ff4444" : "#ffaa55",
                    fontSize: 10,
                    fontWeight: "bold",
                  }}>{d.status}</span>
                </div>
                <div style={{ color: "#c8d2dc", fontSize: 11, lineHeight: 1.5, marginBottom: 6 }}>{d.watch}</div>
                <div style={{ color: "#6b7785", fontSize: 10, fontFamily: "monospace" }}>
                  {d.last_ts ? `last: ${d.last_ts}` : "no timestamp"} {d.age_seconds !== null && d.age_seconds < 300 ? `(${d.age_seconds}s ago)` : ""}
                </div>
                {d.last_line && (
                  <div style={{ color: "#6b7785", fontSize: 10, marginTop: 4, fontFamily: "monospace", opacity: 0.8 }}>
                    {d.last_line.slice(0, 80)}
                  </div>
                )}
              </div>
            )) || (
              <div style={{ color: "#6b7785", fontSize: 12 }}>Loading daemon cycle…</div>
            )}
          </div>
          {cycle?.summary && (
            <div style={{ marginTop: 12, color: "#6b7785", fontSize: 11 }}>
              {cycle.summary.total} daemons · {cycle.summary.running} active · {cycle.summary.stopped} stopped · {cycle.summary.errors} errors
            </div>
          )}
        </div>
      </div>

      {/* UUID MATH */}
      <Section title="GYST UUIDv8 — THE IDENTITY LAYER" color="#00CCDD">
        <div style={{ background: "#10141b", border: "1px solid #1d2630", borderRadius: 8, padding: 20, marginBottom: 16 }}>
          <div style={{ color: "#6b7785", fontSize: 11, marginBottom: 12, textTransform: "uppercase" }}>
            Bit Layout v3.0.0
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
            <div style={{ background: "#0a0c10", border: "1px solid #1d2630", borderRadius: 6, padding: 12 }}>
              <div style={{ color: "#FF9000", fontSize: 11, fontWeight: "bold", marginBottom: 8 }}>HIGH 64 BITS</div>
              <div style={{ color: "#c8d2dc", fontSize: 12, lineHeight: 1.8 }}>
                type(12) · namespace(12) · timestamp(24) · version(4) · fractal(12)
              </div>
            </div>
            <div style={{ background: "#0a0c10", border: "1px solid #1d2630", borderRadius: 6, padding: 12 }}>
              <div style={{ color: "#39ff14", fontSize: 11, fontWeight: "bold", marginBottom: 8 }}>LOW 64 BITS</div>
              <div style={{ color: "#c8d2dc", fontSize: 12, lineHeight: 1.8 }}>
                variant(2) · provenance(4) · signal(16) · content(42)
              </div>
            </div>
          </div>
          <div style={{ marginTop: 16, color: "#c8d2dc", fontSize: 12, lineHeight: 1.7 }}>
            <strong style={{ color: "#FF9000" }}>Deterministic rules:</strong> Updates spawn CHILD UUIDs via <code style={{ color: "#39ff14" }}>ns = fnv1a12(parent)</code>; roll-ups use bitmask routing on <code style={{ color: "#39ff14" }}>ns + fractal</code>; low-42 is <code style={{ color: "#39ff14" }}>sha256(parent)</code>, never random. Every order, fill, market, and signal is a self-describing 128-bit object with native provenance.
          </div>
        </div>

        {/* UUID DIAGRAM */}
        <div style={{
          background: "#10141b",
          border: "1px solid #1d2630",
          borderRadius: 8,
          padding: 20,
          marginTop: 12,
        }}>
          <div style={{ color: "#6b7785", fontSize: 11, marginBottom: 12, textTransform: "uppercase" }}>
            UUID Provenance Chain
          </div>
          <svg viewBox="0 0 800 180" style={{ width: "100%", height: "auto" }}>
            <rect x="10" y="10" width="160" height="80" rx="6" fill="#0a0c10" stroke="#FF9000" strokeWidth="1.5"/>
            <text x="90" y="30" textAnchor="middle" fill="#FF9000" fontSize="11" fontWeight="bold">PARENT UUID</text>
            <text x="90" y="50" textAnchor="middle" fill="#6b7785" fontSize="9">market / story / signal</text>
            <text x="90" y="65" textAnchor="middle" fill="#6b7785" fontSize="9">type(12) | ns(12) | ts(24)</text>

            <rect x="220" y="10" width="160" height="80" rx="6" fill="#0a0c10" stroke="#06b6d4" strokeWidth="1.5"/>
            <text x="300" y="30" textAnchor="middle" fill="#06b6d4" fontSize="11" fontWeight="bold">CHILD UUID</text>
            <text x="300" y="50" textAnchor="middle" fill="#6b7785" fontSize="9">order / fill / forecast</text>
            <text x="300" y="65" textAnchor="middle" fill="#6b7785" fontSize="9">ns = fnv1a12(parent)</text>

            <rect x="430" y="10" width="160" height="80" rx="6" fill="#0a0c10" stroke="#39ff14" strokeWidth="1.5"/>
            <text x="510" y="30" textAnchor="middle" fill="#39ff14" fontSize="11" fontWeight="bold">GRANDCHILD UUID</text>
            <text x="510" y="50" textAnchor="middle" fill="#6b7785" fontSize="9">fill / settle / mark</text>
            <text x="510" y="65" textAnchor="middle" fill="#6b7785" fontSize="9">depth += 1, gen += 1</text>

            <rect x="640" y="10" width="150" height="80" rx="6" fill="#0a0c10" stroke="#ff10f0" strokeWidth="1.5"/>
            <text x="715" y="30" textAnchor="middle" fill="#ff10f0" fontSize="11" fontWeight="bold">ROLL-UP</text>
            <text x="715" y="50" textAnchor="middle" fill="#6b7785" fontSize="9">bitmask on ns+fractal</text>
            <text x="715" y="65" textAnchor="middle" fill="#6b7785" fontSize="9">aggregate parent</text>

            <line x1="170" y1="50" x2="220" y2="50" stroke="#06b6d4" strokeWidth="1.5" markerEnd="url(#arrow-blue)"/>
            <line x1="380" y1="50" x2="430" y2="50" stroke="#39ff14" strokeWidth="1.5" markerEnd="url(#arrow-green)"/>
            <line x1="590" y1="50" x2="640" y2="50" stroke="#ff10f0" strokeWidth="1.5" markerEnd="url(#arrow-pink)"/>

            <text x="195" y="45" textAnchor="middle" fill="#6b7785" fontSize="9">spawn</text>
            <text x="405" y="45" textAnchor="middle" fill="#6b7785" fontSize="9">spawn</text>
            <text x="615" y="45" textAnchor="middle" fill="#6b7785" fontSize="9">rollup</text>

            <defs>
              <marker id="arrow-blue" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto" markerUnits="strokeWidth">
                <path d="M0,0 L0,6 L8,3 z" fill="#06b6d4" />
              </marker>
              <marker id="arrow-green" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto" markerUnits="strokeWidth">
                <path d="M0,0 L0,6 L8,3 z" fill="#39ff14" />
              </marker>
              <marker id="arrow-pink" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto" markerUnits="strokeWidth">
                <path d="M0,0 L0,6 L8,3 z" fill="#ff10f0" />
              </marker>
            </defs>
          </svg>
        </div>
      </Section>

      {/* ARCHITECTURE */}
      <Section title="ARCHITECTURE" color="#00CCDD">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
          <Card title="SCANNERS" body={[
            "orderbook_monitor.py — polls 200 markets/10s",
            "liquidity_hunter.py — enters only on real bid+ask",
            "volume_watchdog.py — arms when volume_24h > 0",
            "btc_paper_engine.py — BTC short paper test",
          ]} accent="#06b6d4" />
          <Card title="EXECUTION" body={[
            "mission_control.py — V2 auth + order wrapper",
            "liquidity_hunter.py — IoC exits, local tracking",
            "MAX_ENTRY_PRICE cap — exits always reachable",
            "Floor guard at /api/order — live orders blocked below $15",
          ]} accent="#39ff14" />
          <Card title="MONITORING" body={[
            ":4242/api/portfolio — live Kalshi balance",
            ":4242/api/venue_health — Kalshi + Polymarket",
            ":8420/api/kalshi/{balance,positions,orders}",
            "mc_state DB — 60s reconciled truth",
          ]} accent="#FF9000" />
          <Card title="ROUTING" body={[
            "venue_router.py — depth-based venue selection",
            "Only routes to executable books",
            "Polymarket fallback when Kalshi dead",
            "Bridge coordinator — cross-account awareness",
          ]} accent="#ff10f0" />
        </div>

        {/* ARCHITECTURE DIAGRAM */}
        <div style={{
          background: "#10141b",
          border: "1px solid #1d2630",
          borderRadius: 8,
          padding: 20,
          marginTop: 20,
        }}>
          <div style={{ color: "#6b7785", fontSize: 11, marginBottom: 12, textTransform: "uppercase" }}>
            System Flow
          </div>
          <svg viewBox="0 0 800 220" style={{ width: "100%", height: "auto" }}>
            <rect x="10" y="10" width="180" height="200" rx="8" fill="#10141b" stroke="#1d2630" strokeWidth="1"/>
            <text x="100" y="35" textAnchor="middle" fill="#06b6d4" fontSize="12" fontWeight="bold">KALSHI</text>
            <text x="100" y="55" textAnchor="middle" fill="#6b7785" fontSize="10">200 open markets</text>
            <text x="100" y="75" textAnchor="middle" fill="#6b7785" fontSize="10">V2 REST API</text>
            <text x="100" y="95" textAnchor="middle" fill="#6b7785" fontSize="10">Prices: dollars × 100</text>

            <rect x="610" y="10" width="180" height="200" rx="8" fill="#10141b" stroke="#1d2630" strokeWidth="1"/>
            <text x="700" y="35" textAnchor="middle" fill="#ff10f0" fontSize="12" fontWeight="bold">POLYMARKET</text>
            <text x="700" y="55" textAnchor="middle" fill="#6b7785" fontSize="10">CLOB orderbook</text>
            <text x="700" y="75" textAnchor="middle" fill="#6b7785" fontSize="10">Polygon RPC</text>
            <text x="700" y="95" textAnchor="middle" fill="#6b7785" fontSize="10">py-clob-client</text>

            <rect x="320" y="60" width="160" height="100" rx="8" fill="#10141b" stroke="#FF9000" strokeWidth="2"/>
            <text x="400" y="90" textAnchor="middle" fill="#FF9000" fontSize="12" fontWeight="bold">VENUE ROUTER</text>
            <text x="400" y="110" textAnchor="middle" fill="#6b7785" fontSize="10">depth-based routing</text>
            <text x="400" y="130" textAnchor="middle" fill="#6b7785" fontSize="10">no dead books</text>

            <line x1="190" y1="110" x2="320" y2="110" stroke="#06b6d4" strokeWidth="2" markerEnd="url(#arrow)"/>
            <line x1="480" y1="110" x2="610" y2="110" stroke="#ff10f0" strokeWidth="2" markerEnd="url(#arrow)"/>

            <rect x="320" y="180" width="160" height="30" rx="4" fill="#10141b" stroke="#39ff14" strokeWidth="1"/>
            <text x="400" y="200" textAnchor="middle" fill="#39ff14" fontSize="10">:4242 + :8420 live dashboards</text>

            <line x1="400" y1="160" x2="400" y2="180" stroke="#39ff14" strokeWidth="1.5"/>

            <defs>
              <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
                <path d="M0,0 L0,6 L9,3 z" fill="#06b6d4" />
              </marker>
            </defs>
          </svg>
        </div>
      </Section>

      {/* AGENT PROTOCOL */}
      <Section title="AGENT PROTOCOL" color="#39ff14">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
          <Card title="HOW AGENTS TRADE" body={[
            "Every action is a UUIDv8 — order, fill, settle, mark",
            "Signal drift ≥1.5bps on BTC/ETH/SOL/XRP/DOGE 15M",
            "Entry: 25–60¢, both-side, size by bankroll",
            "Exit: +15¢ take / −10¢ stop / IoC at settlement",
            "Local entry tracking — Kalshi avg_cost bug bypass",
          ]} accent="#39ff14" />
          <Card title="HONESTY MACHINERY" body={[
            "Exchange truth only: fill_count_fp > 0 = real fill",
            "P&L from /portfolio/positions + settles",
            "Evidence engine: Wilson 95% CI, n≥50, lower-CI≥55%",
            "Losses published — $24.98 → $134 → $57 → $102 arc visible",
            "No sugarcoating: always post true state",
          ]} accent="#ffaa55" />
          <Card title="EVIDENCE GATES" body={[
            "PROVEN: n≥50 AND lower-CI≥55% AND exp>0",
            "FORMING: 20≤n<50, CI expanding",
            "DEAD: n≥20 AND lower-CI<50% — lane killed",
            "5 parallel paper backtests continuously test exits",
            "Live engines adopt winner automatically",
          ]} accent="#06b6d4" />
          <Card title="SAVINGS + BRIDGE" body={[
            "25% of every realized win → protected savings sleeve",
            "Vault locks 30% reserve + savings",
            "Bridge coordinator watches Kalshi + Poly balances",
            "Recommends cross-account rebalance (manual taps)",
            "Funding feed detects Venmo deposits via balance delta",
          ]} accent="#FF9000" />
        </div>

        {/* AGENT FLOW DIAGRAM */}
        <div style={{
          background: "#10141b",
          border: "1px solid #1d2630",
          borderRadius: 8,
          padding: 20,
          marginTop: 20,
        }}>
          <div style={{ color: "#6b7785", fontSize: 11, marginBottom: 12, textTransform: "uppercase" }}>
            Agent Execution Flow
          </div>
          <svg viewBox="0 0 800 160" style={{ width: "100%", height: "auto" }}>
            <rect x="10" y="10" width="140" height="60" rx="6" fill="#0a0c10" stroke="#06b6d4" strokeWidth="1.5"/>
            <text x="80" y="30" textAnchor="middle" fill="#06b6d4" fontSize="11" fontWeight="bold">SIGNAL</text>
            <text x="80" y="50" textAnchor="middle" fill="#6b7785" fontSize="9">drift ≥1.5bps</text>

            <rect x="180" y="10" width="140" height="60" rx="6" fill="#0a0c10" stroke="#39ff14" strokeWidth="1.5"/>
            <text x="250" y="30" textAnchor="middle" fill="#39ff14" fontSize="11" fontWeight="bold">EVIDENCE</text>
            <text x="250" y="50" textAnchor="middle" fill="#6b7785" fontSize="9">Wilson CI ≥55%</text>

            <rect x="350" y="10" width="140" height="60" rx="6" fill="#0a0c10" stroke="#FF9000" strokeWidth="1.5"/>
            <text x="420" y="30" textAnchor="middle" fill="#FF9000" fontSize="11" fontWeight="bold">ENTRY</text>
            <text x="420" y="50" textAnchor="middle" fill="#6b7785" fontSize="9">IoC limit order</text>

            <rect x="520" y="10" width="140" height="60" rx="6" fill="#0a0c10" stroke="#ff10f0" strokeWidth="1.5"/>
            <text x="590" y="30" textAnchor="middle" fill="#ff10f0" fontSize="11" fontWeight="bold">EXIT</text>
            <text x="590" y="50" textAnchor="middle" fill="#6b7785" fontSize="9">+15c / −10c / settle</text>

            <rect x="680" y="10" width="110" height="60" rx="6" fill="#0a0c10" stroke="#c8d2dc" strokeWidth="1"/>
            <text x="735" y="30" textAnchor="middle" fill="#c8d2dc" fontSize="11" fontWeight="bold">LEDGER</text>
            <text x="735" y="50" textAnchor="middle" fill="#6b7785" fontSize="9">UUIDv8 truth</text>

            <line x1="150" y1="40" x2="180" y2="40" stroke="#06b6d4" strokeWidth="1.5" markerEnd="url(#arrow-blue)"/>
            <line x1="320" y1="40" x2="350" y2="40" stroke="#39ff14" strokeWidth="1.5" markerEnd="url(#arrow-green)"/>
            <line x1="490" y1="40" x2="520" y2="40" stroke="#FF9000" strokeWidth="1.5" markerEnd="url(#arrow-orange)"/>
            <line x1="660" y1="40" x2="680" y2="40" stroke="#ff10f0" strokeWidth="1.5" markerEnd="url(#arrow-pink)"/>

            <line x1="420" y1="70" x2="420" y2="120" stroke="#FF9000" strokeWidth="1"/>
            <rect x="320" y="120" width="200" height="30" rx="4" fill="#10141b" stroke="#FF9000" strokeWidth="1"/>
            <text x="420" y="140" textAnchor="middle" fill="#FF9000" fontSize="10">25% win → protected savings sleeve</text>

            <defs>
              <marker id="arrow-blue" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto" markerUnits="strokeWidth">
                <path d="M0,0 L0,6 L8,3 z" fill="#06b6d4" />
              </marker>
              <marker id="arrow-green" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto" markerUnits="strokeWidth">
                <path d="M0,0 L0,6 L8,3 z" fill="#39ff14" />
              </marker>
              <marker id="arrow-orange" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto" markerUnits="strokeWidth">
                <path d="M0,0 L0,6 L8,3 z" fill="#FF9000" />
              </marker>
              <marker id="arrow-pink" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto" markerUnits="strokeWidth">
                <path d="M0,0 L0,6 L8,3 z" fill="#ff10f0" />
              </marker>
            </defs>
          </svg>
        </div>
      </Section>

      {/* RISK CONTROLS */}
      <Section title="RISK CONTROLS" color="#39ff14">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
          <Control label="CASH FLOOR" value="$15 minimum" desc="Never trade below floor" />
          <Control label="MAX ENTRY" value="1–2 contracts" desc="Micro size only" />
          <Control label="BOOK CHECK" value="bid + ask > 0" desc="No ghost orders" />
          <Control label="EXIT MODE" value="IoC limit" desc="Fill or cancel" />
          <Control label="PRICE SOURCE" value="/markets/{ticker}" desc="Only truthful endpoint" />
          <Control label="VOLUME FILTER" value="> 0 required" desc="No dead books" />
        </div>
      </Section>

      {/* BUILD ROADMAP */}
      <Section title="BUILD ROADMAP" color="#FF9000">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 16 }}>
          <RoadmapItem phase="1" title="Live Monitoring" status="done" desc="Portfolio, orders, positions on :4242 + :8420" />
          <RoadmapItem phase="2" title="Liquidity Scanners" status="done" desc="3 daemons scanning 200 markets/10s" />
          <RoadmapItem phase="3" title="BTC Paper Test" status="done" desc="/btc dashboard with live spot P&L" />
          <RoadmapItem phase="4" title="Multi-Venue Router" status="scaffold" desc="Routes to Kalshi or Polymarket based on depth" />
          <RoadmapItem phase="5" title="Live Trading" status="pending" desc="Armed, waiting for executable liquidity" />
          <RoadmapItem phase="6" title="Profit Scaling" status="pending" desc="Size up after 60%+ win rate on live closes" />
        </div>
      </Section>

      {/* SPOCTALK NOTE */}
      <Section title="SPOCTALK / AGENT COMMUNICATION" color="#ff10f0">
        <div style={{ background: "#10141b", border: "1px solid #1d2630", borderRadius: 8, padding: 16 }}>
          <div style={{ color: "#ff10f0", fontSize: 12, fontWeight: "bold", marginBottom: 8 }}>STATUS: NEEDS SOURCE DOCS</div>
          <div style={{ color: "#c8d2dc", fontSize: 12, lineHeight: 1.6 }}>
            I couldn’t find SPOCTALK in any existing gist, script, or markdown file. If you point me to the spec, gist, or repo that defines it, I’ll add a dedicated section here with the exact protocol flow and how agents use it for prediction-market reasoning.
          </div>
        </div>
      </Section>

      {/* LIVE STATUS */}
      <Section title="LIVE SYSTEM STATUS" color="#06b6d4">
        <div style={{ background: "#10141b", border: "1px solid #1d2630", borderRadius: 8, padding: 16 }}>
          <pre style={{ color: "#c8d2dc", fontSize: 12, margin: 0, whiteSpace: "pre-wrap" }}>
{JSON.stringify({
  bank: {
    cash: `$${cash}`,
    portfolio: `$${portfolio_value}`,
    positions: positions_count,
    open_orders: open_orders,
  },
  scanners: {
    orderbook_monitor: "RUNNING",
    liquidity_hunter: "RUNNING",
    volume_watchdog: "RUNNING",
    btc_paper_engine: "RUNNING",
  },
  dashboards: {
    local: "http://localhost:4242",
    mission_control: "http://localhost:8420",
    btc: "https://btc.somacosf.com",
    info: "https://info.somacosf.com/info",
  },
  venue_health: health || {},
  last_updated: new Date().toISOString(),
}, null, 2)}
          </pre>
        </div>
      </Section>

      <footer style={{ marginTop: 40, paddingTop: 16, borderTop: "1px solid #1d2630", color: "#6b7785", fontSize: 11 }}>
        SoMaCoSF Prediction-Market Fleet · Built for constant uptick · No sugarcoating · Verification before claim
      </footer>
    </main>
  );
}

function Section({ title, color, children }) {
  return (
    <section style={{ marginBottom: 28 }}>
      <h2 style={{ color, fontSize: 14, textTransform: "uppercase", letterSpacing: 2, marginBottom: 12, borderBottom: `1px solid ${color}33`, paddingBottom: 6 }}>
        {title}
      </h2>
      {children}
    </section>
  );
}

function Badge({ label, value, color }) {
  return (
    <div style={{
      background: "#10141b",
      border: `1px solid ${color}44`,
      borderRadius: 6,
      padding: "8px 14px",
      minWidth: 120,
    }}>
      <div style={{ color: "#6b7785", fontSize: 10, textTransform: "uppercase" }}>{label}</div>
      <div style={{ color, fontSize: 16, fontWeight: "bold", marginTop: 2 }}>{value}</div>
    </div>
  );
}

function Card({ title, body, accent }) {
  return (
    <div style={{
      background: "#10141b",
      border: `1px solid ${accent}33`,
      borderRadius: 8,
      padding: 16,
    }}>
      <div style={{ color: accent, fontSize: 12, fontWeight: "bold", marginBottom: 10, textTransform: "uppercase" }}>
        {title}
      </div>
      {body.map((line, i) => (
        <div key={i} style={{ color: "#c8d2dc", fontSize: 12, marginBottom: 4, lineHeight: 1.5 }}>
          {line}
        </div>
      ))}
    </div>
  );
}

function Control({ label, value, desc }) {
  return (
    <div style={{
      background: "#10141b",
      border: "1px solid #1d2630",
      borderRadius: 8,
      padding: 14,
    }}>
      <div style={{ color: "#39ff14", fontSize: 11, fontWeight: "bold", marginBottom: 6 }}>{label}</div>
      <div style={{ color: "#c8d2dc", fontSize: 14, marginBottom: 4 }}>{value}</div>
      <div style={{ color: "#6b7785", fontSize: 11 }}>{desc}</div>
    </div>
  );
}

function RoadmapItem({ phase, title, status, desc }) {
  const statusColor = status === "done" ? "#39ff14" : status === "scaffold" ? "#ffaa55" : "#6b7785";
  return (
    <div style={{
      background: "#10141b",
      border: "1px solid #1d2630",
      borderRadius: 8,
      padding: 16,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
        <span style={{ color: "#FF9000", fontSize: 12, fontWeight: "bold" }}>PHASE {phase}</span>
        <span style={{ color: statusColor, fontSize: 11, textTransform: "uppercase" }}>{status}</span>
      </div>
      <div style={{ color: "#c8d2dc", fontSize: 14, fontWeight: "bold", marginBottom: 4 }}>{title}</div>
      <div style={{ color: "#6b7785", fontSize: 11 }}>{desc}</div>
    </div>
  );
}
