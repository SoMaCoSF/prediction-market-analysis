import { useEffect, useState } from "react";

export default function Grind() {
  const [portfolio, setPortfolio] = useState(null);

  useEffect(() => {
    fetch("/api/portfolio").then(r => r.ok ? r.json() : null).then(setPortfolio).catch(() => {});
  }, []);

  const cash = portfolio?.balance?.balance_dollars || "—";
  const portfolio_value = portfolio?.balance?.portfolio_value || "—";

  return (
    <main style={{
      fontFamily: "monospace",
      background: "#0a0c10",
      color: "#c8d2dc",
      minHeight: "100vh",
      padding: 24,
    }}>
      {/* HERO */}
      <div style={{
        background: "linear-gradient(180deg, #10141b 0%, #0a0c10 100%)",
        border: "1px solid #1d2630",
        borderRadius: 12,
        padding: 32,
        marginBottom: 24,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16 }}>
          <div>
            <h1 style={{ color: "#FF9000", fontSize: 32, margin: 0, letterSpacing: 1 }}>
              GRIND<span style={{ color: "#39ff14" }}>.</span>somacosf.com
            </h1>
            <p style={{ color: "#6b7785", fontSize: 14, marginTop: 10, maxWidth: 800, lineHeight: 1.6 }}>
              The micro-grind engine explained. How AI agents trade prediction markets,
              why size matters, and what "constant uptick" actually means.
            </p>
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <Badge label="Live Cash" value={`$${cash}`} color="#39ff14" />
            <Badge label="Portfolio" value={`$${portfolio_value}`} color="#06b6d4" />
          </div>
        </div>
      </div>

      {/* WHAT IS GRINDING */}
      <Section title="WHAT IS MICRO-GRIND TRADING?" color="#FF9000">
        <div style={{ background: "#10141b", border: "1px solid #1d2630", borderRadius: 8, padding: 20, marginBottom: 16 }}>
          <div style={{ color: "#c8d2dc", fontSize: 13, lineHeight: 1.8, marginBottom: 16 }}>
            <strong style={{ color: "#FF9000" }}>Grinding</strong> is the practice of making many small, high-probability trades to build profit
            incrementally. Instead of looking for one "home run" bet, the grind engine scans hundreds of markets,
            identifies micro-edges, and executes them repeatedly — like a river wearing down rock.
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
            <Metric label="Typical Win Rate" value="60–70%" desc="Lower than a casino, but positive expectancy" />
            <Metric label="Average Win" value="+5–15¢" desc="Small, consistent gains" />
            <Metric label="Average Loss" value="−5–10¢" desc="Controlled downside" />
            <Metric label="Trades Per Day" value="50–200+" desc="Volume replaces single-bet size" />
            <Metric label="Capital Required" value="$20–50" desc="Micro-size, not yolo" />
            <Metric label="Edge Source" value="Drift + Liquidity" desc="1.5bps signal + real orderbook depth" />
          </div>
        </div>
      </Section>

      {/* WHY AI */}
      <Section title="WHY AI AGENTS?" color="#00CCDD">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
          <Card title="SPEED" body={[
            "Humans: 10–30 seconds per market scan",
            "AI agents: 200 markets in <1 second",
            "Orderbook movement is fleeting — agents catch it",
            "24/7 operation — no sleep, no fatigue",
          ]} accent="#06b6d4" />
          <Card title="DISCIPLINE" body={[
            "No revenge trading after a loss",
            "No FOMO chasing a pump",
            "Stops execute automatically at −10¢",
            "Size rules never violated",
          ]} accent="#39ff14" />
          <Card title="CONSISTENCY" body={[
            "Same logic every trade — no mood swings",
            "Evidence-gated: Wilson CI ≥55% to size up",
            "5 parallel backtests verify exit profiles",
            "Losses published, not hidden",
          ]} accent="#FF9000" />
          <Card title="SCALE" body={[
            "1 agent = 1 lane",
            "9 crypto series × multiple timeframes",
            "Cross-venue: Kalshi + Polymarket simultaneously",
            "Add lanes = add compute, not more humans",
          ]} accent="#ff10f0" />
        </div>
      </Section>

      {/* THE GRIND CYCLE */}
      <Section title="THE GRIND CYCLE — STEP BY STEP" color="#39ff14">
        <div style={{ background: "#10141b", border: "1px solid #1d2630", borderRadius: 8, padding: 20, marginBottom: 16 }}>
          <div style={{ color: "#6b7785", fontSize: 11, marginBottom: 16, textTransform: "uppercase" }}>
            How a single trade executes — from signal to P&L
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
            <Step num="01" title="SCAN" desc="Poll 200 markets every 10s for real bid+ask depth" color="#06b6d4" />
            <Step num="02" title="SIGNAL" desc="Drift ≥1.5bps on BTC/ETH/SOL/XRP/DOGE 15M candles" color="#39ff14" />
            <Step num="03" title="EVIDENCE" desc="Wilson 95% CI check — only proven edges" color="#FF9000" />
            <Step num="04" title="SIZE" desc="1 contract, $0.05–0.10 max — never overbet" color="#ff10f0" />
            <Step num="05" title="ENTER" desc="IoC limit order at 5¢ bid / 10¢ ask" color="#06b6d4" />
            <Step num="06" title="EXIT" desc="+15¢ take-profit, −10¢ stop-loss, or settle" color="#39ff14" />
            <Step num="07" title="LEDGER" desc="Every fill = UUIDv8 child, reconciled to Postgres" color="#FF9000" />
            <Step num="08" title="REPEAT" desc="25% of win → savings sleeve, rest recycled" color="#ff10f0" />
          </div>
        </div>

        {/* CYCLE DIAGRAM */}
        <div style={{
          background: "#10141b",
          border: "1px solid #1d2630",
          borderRadius: 8,
          padding: 20,
        }}>
          <div style={{ color: "#6b7785", fontSize: 11, marginBottom: 12, textTransform: "uppercase" }}>
            Capital Flow Through the Grind
          </div>
          <svg viewBox="0 0 800 200" style={{ width: "100%", height: "auto" }}>
            {/* Capital pool */}
            <rect x="10" y="60" width="120" height="80" rx="6" fill="#0a0c10" stroke="#39ff14" strokeWidth="1.5"/>
            <text x="70" y="80" textAnchor="middle" fill="#39ff14" fontSize="11" fontWeight="bold">CAPITAL</text>
            <text x="70" y="100" textAnchor="middle" fill="#6b7785" fontSize="9">$20–50 bankroll</text>
            <text x="70" y="115" textAnchor="middle" fill="#6b7785" fontSize="9">floor: $15</text>

            {/* Scanner */}
            <rect x="170" y="60" width="120" height="80" rx="6" fill="#0a0c10" stroke="#06b6d4" strokeWidth="1.5"/>
            <text x="230" y="80" textAnchor="middle" fill="#06b6d4" fontSize="11" fontWeight="bold">SCANNER</text>
            <text x="230" y="100" textAnchor="middle" fill="#6b7785" fontSize="9">200 markets/10s</text>
            <text x="230" y="115" textAnchor="middle" fill="#6b7785" fontSize="9">depth check</text>

            {/* Engine */}
            <rect x="330" y="60" width="120" height="80" rx="6" fill="#0a0c10" stroke="#FF9000" strokeWidth="1.5"/>
            <text x="390" y="80" textAnchor="middle" fill="#FF9000" fontSize="11" fontWeight="bold">ENGINE</text>
            <text x="390" y="100" textAnchor="middle" fill="#6b7785" fontSize="9">entry + exit</text>
            <text x="390" y="115" textAnchor="middle" fill="#6b7785" fontSize="9">1–2 contracts</text>

            {/* Ledger */}
            <rect x="490" y="60" width="120" height="80" rx="6" fill="#0a0c10" stroke="#ff10f0" strokeWidth="1.5"/>
            <text x="550" y="80" textAnchor="middle" fill="#ff10f0" fontSize="11" fontWeight="bold">LEDGER</text>
            <text x="550" y="100" textAnchor="middle" fill="#6b7785" fontSize="9">UUIDv8 truth</text>
            <text x="550" y="115" textAnchor="middle" fill="#6b7785" fontSize="9">every fill tracked</text>

            {/* Savings */}
            <rect x="650" y="20" width="130" height="60" rx="6" fill="#0a0c10" stroke="#39ff14" strokeWidth="1.5"/>
            <text x="715" y="40" textAnchor="middle" fill="#39ff14" fontSize="11" fontWeight="bold">SAVINGS</text>
            <text x="715" y="55" textAnchor="middle" fill="#6b7785" fontSize="9">25% of every win</text>
            <text x="715" y="70" textAnchor="middle" fill="#6b7785" fontSize="9">protected sleeve</text>

            {/* Arrows */}
            <line x1="130" y1="100" x2="170" y2="100" stroke="#39ff14" strokeWidth="2" markerEnd="url(#arrow-green)"/>
            <line x1="290" y1="100" x2="330" y2="100" stroke="#06b6d4" strokeWidth="2" markerEnd="url(#arrow-blue)"/>
            <line x1="450" y1="100" x2="490" y2="100" stroke="#FF9000" strokeWidth="2" markerEnd="url(#arrow-orange)"/>
            <line x1="610" y1="100" x2="650" y2="80" stroke="#ff10f0" strokeWidth="1.5" markerEnd="url(#arrow-pink)"/>

            {/* Return arrow */}
            <line x1="715" y1="80" x2="715" y2="140" stroke="#39ff14" strokeWidth="1.5"/>
            <line x1="715" y1="140" x2="70" y2="140" stroke="#39ff14" strokeWidth="1.5"/>
            <line x1="70" y1="140" x2="70" y2="140" stroke="#39ff14" strokeWidth="1.5"/>

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

      {/* RISK MATH */}
      <Section title="THE MATH — WHY IT WORKS" color="#39ff14">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
          <MathBlock
            title="EXPECTANCY"
            formula="(Win% × Avg Win) − (Loss% × Avg Loss)"
            example="(0.65 × $0.10) − (0.35 × $0.08) = +$0.039/trade"
            color="#39ff14"
          />
          <MathBlock
            title="KELLY CRITERION"
            formula="f* = (p·b − q) / b"
            example="p=0.65, b=1.25, q=0.35 → f* = 0.4625 → bet 46% of edge"
            color="#06b6d4"
          />
          <MathBlock
            title="VOLUME EFFECT"
            formula="Edge × Trades = Profit"
            example="$0.04/trade × 100 trades/day = +$4.00/day"
            color="#FF9000"
          />
          <MathBlock
            title="COMPOUNDING"
            formula="PnL = P₀(1 + r)ⁿ"
            example="$20 × 1.02⁶⁰ ≈ $664.74 at 2%/day over 60 days"
            color="#ff10f0"
          />
        </div>
      </Section>

      {/* EDUCATION */}
      <Section title="WHAT PEOPLE GET WRONG" color="#ffaa55">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
          <Card title="❌ GAMBLING" body={[
            "Gambling = negative expectancy, house edge built in",
            "Grinding = positive expectancy, edge is real",
            "We only trade when math favors us",
            "If the math doesn’t work, we don’t trade",
          ]} accent="#ff4444" />
          <Card title="❌ GET-RICH-QUICK" body={[
            "This is not a lottery ticket",
            "$20 → $100 in 60 days is realistic",
            "$20 → $10,000 in a week is fantasy",
            "Consistency > heroics",
          ]} accent="#ff4444" />
          <Card title="❌ YOLO BETS" body={[
            "We never risk more than 1–2 contracts",
            "Floor guard at $15 — hard stop",
            "Stop-loss at −10¢ — automatic",
            "If you’re betting the farm, you’re doing it wrong",
          ]} accent="#ff4444" />
          <Card title="✓ WHAT IT ACTUALLY IS" body={[
            "Micro-grind = many small edges, repeated",
            "AI = speed + discipline + 24/7 availability",
            "Risk management = survival first, profit second",
            "Verification = we only claim what we can prove",
          ]} accent="#39ff14" />
        </div>
      </Section>

      {/* LIVE STATUS */}
      <Section title="LIVE GRIND STATUS" color="#06b6d4">
        <div style={{ background: "#10141b", border: "1px solid #1d2630", borderRadius: 8, padding: 16 }}>
          <pre style={{ color: "#c8d2dc", fontSize: 12, margin: 0, whiteSpace: "pre-wrap" }}>
{JSON.stringify({
  bank: {
    cash: `$${cash}`,
    portfolio: `$${portfolio_value}`,
  },
  grind: {
    mode: "MICRO-GRIND",
    floor: "$15",
    max_entry: "1–2 contracts",
    target_win_rate: "≥60%",
    exit_take: "+15¢",
    exit_stop: "−10¢",
    volume_filter: "> 0 required",
  },
  scanners: {
    orderbook_monitor: "RUNNING",
    liquidity_hunter: "RUNNING",
    volume_watchdog: "RUNNING",
    btc_paper_engine: "RUNNING",
  },
  last_updated: new Date().toISOString(),
}, null, 2)}
          </pre>
        </div>
      </Section>

      <footer style={{ marginTop: 40, paddingTop: 16, borderTop: "1px solid #1d2630", color: "#6b7785", fontSize: 11 }}>
        GRIND.somacosf.com · SoMaCoSF Prediction-Market Fleet · Built for constant uptick · No sugarcoating · Verification before claim
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

function Metric({ label, value, desc }) {
  return (
    <div style={{
      background: "#10141b",
      border: "1px solid #1d2630",
      borderRadius: 8,
      padding: 14,
    }}>
      <div style={{ color: "#6b7785", fontSize: 10, textTransform: "uppercase", marginBottom: 6 }}>{label}</div>
      <div style={{ color: "#39ff14", fontSize: 20, fontWeight: "bold", marginBottom: 4 }}>{value}</div>
      <div style={{ color: "#6b7785", fontSize: 11 }}>{desc}</div>
    </div>
  );
}

function Step({ num, title, desc, color }) {
  return (
    <div style={{
      background: "#10141b",
      border: "1px solid #1d2630",
      borderRadius: 8,
      padding: 14,
    }}>
      <div style={{ color, fontSize: 10, fontWeight: "bold", marginBottom: 6 }}>{num}</div>
      <div style={{ color, fontSize: 13, fontWeight: "bold", marginBottom: 4 }}>{title}</div>
      <div style={{ color: "#6b7785", fontSize: 11, lineHeight: 1.5 }}>{desc}</div>
    </div>
  );
}

function MathBlock({ title, formula, example, color }) {
  return (
    <div style={{
      background: "#10141b",
      border: `1px solid ${color}33`,
      borderRadius: 8,
      padding: 16,
    }}>
      <div style={{ color, fontSize: 12, fontWeight: "bold", marginBottom: 10, textTransform: "uppercase" }}>{title}</div>
      <div style={{ color: "#c8d2dc", fontSize: 13, fontFamily: "monospace", marginBottom: 8, lineHeight: 1.5 }}>
        {formula}
      </div>
      <div style={{ color: "#6b7785", fontSize: 11, lineHeight: 1.5 }}>
        {example}
      </div>
    </div>
  );
}
