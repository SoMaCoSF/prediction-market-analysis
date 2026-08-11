import { useEffect, useState } from "react";

export default function Info() {
  const [kalshi, setKalshi] = useState(null);
  const [positions, setPositions] = useState(null);
  const [orders, setOrders] = useState(null);
  const [stats, setStats] = useState(null);
  const [whale, setWhale] = useState(null);
  const [settles, setSettles] = useState(null);
  const [cycle, setCycle] = useState(null);

  useEffect(() => {
    const fetchAll = async () => {
      const [k, p, o, s, w, st, c] = await Promise.all([
        fetch("/api/kalshi/balance").then(r => r.ok ? r.json() : null).catch(() => null),
        fetch("/api/kalshi/positions").then(r => r.ok ? r.json() : null).catch(() => null),
        fetch("/api/kalshi/orders").then(r => r.ok ? r.json() : null).catch(() => null),
        fetch("/api/whale/signals").then(r => r.ok ? r.json() : null).catch(() => null),
        fetch("/api/settlements").then(r => r.ok ? r.json() : null).catch(() => null),
        fetch("/api/stats").then(r => r.ok ? r.json() : null).catch(() => null),
        fetch("/api/info/cycle").then(r => r.ok ? r.json() : null).catch(() => null),
      ]);
      setKalshi(k); setPositions(p); setOrders(o);
      setWhale(w); setSettles(st); setStats(s); setCycle(c);
    };
    fetchAll();
    const t = setInterval(fetchAll, 10000);
    return () => clearInterval(t);
  }, []);

  const cash = kalshi?.balance_dollars || "—";
  const portfolio = kalshi?.portfolio_value || "—";
  const positions_count = positions?.event_positions?.length || 0;
  const open_orders = orders?.length || 0;
  const ledger = stats?.ledger || {};
  const kill = stats?.kill || false;
  const keys = stats?.keys || false;

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
              multi-venue liquidity routing, event-driven engine, and real-time monitoring — built for constant uptick.
            </p>
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <Badge label="Status" value={cycle?.summary?.running ? "LIVE" : "OFFLINE"} color={cycle?.summary?.running ? "#39ff14" : "#ffaa55"} />
            <Badge label="Cash" value={`$${cash}`} color="#39ff14" />
            <Badge label="Portfolio" value={`$${portfolio}`} color="#06b6d4" />
            <Badge label="Ledger P&L" value={`${ledger.realized_pnl_cents ? `$${ledger.realized_pnl_cents}¢` : "—"}`} color="#FF9000" />
            <Badge label="Fills" value={ledger.fills || 0} color="#c8d2dc" />
            <Badge label="Kill" value={kill ? "HALT" : "CLEAR"} color={kill ? "#ff4444" : "#39ff14"} />
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
                    fontSize: 10, fontWeight: "bold",
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

      {/* VENUE STATE */}
      <Section title="VENUE STATE" color="#06b6d4">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
          <div style={{ background: "#10141b", border: "1px solid #1d2630", borderRadius: 8, padding: 16 }}>
            <div style={{ color: "#06b6d4", fontSize: 12, fontWeight: "bold", marginBottom: 10, textTransform: "uppercase" }}>Kalshi Status</div>
            <div style={{ color: "#c8d2dc", fontSize: 12, lineHeight: 1.8 }}>
              Cash: ${cash} · Portfolio: ${portfolio} · {positions_count} event positions · {open_orders} open orders<br/>
              Ledger: {ledger.fills || 0} fills · {ledger.orders || 0} orders · {ledger.open_contracts || 0} open contracts<br/>
              Realized P&L: {ledger.realized_pnl_cents ? `${ledger.realized_pnl_cents}¢` : "—"}<br/>
              Kill switch: <span style={{ color: kill ? "#ff4444" : "#39ff14" }}>{kill ? "HALT" : "CLEAR"}</span><br/>
              API keys: <span style={{ color: keys ? "#39ff14" : "#ff4444" }}>{keys ? "PRESENT" : "MISSING"}</span><br/>
              Corpus DB: <span style={{ color: !stats?.corpus?.online ? "#ffaa55" : "#39ff14" }}>{stats?.corpus?.online ? "ONLINE" : "OFFLINE"}</span>
            </div>
          </div>

          <div style={{ background: "#10141b", border: "1px solid #1d2630", borderRadius: 8, padding: 16 }}>
            <div style={{ color: "#ff10f0", fontSize: 12, fontWeight: "bold", marginBottom: 10, textTransform: "uppercase" }}>Polymarket</div>
            <div style={{ color: "#c8d2dc", fontSize: 12, lineHeight: 1.8 }}>
              Wallet: <code>0xbC66…Dd40</code> (Polygon)<br/>
              Status: <span style={{ color: "#ffaa55" }}>SIGNAL ONLY — unfunded</span><br/>
              Execution: armed when USDC lands<br/>
              Whale copier: live via Gamma API<br/>
              Cross-venue arb: scanning<br/>
              Min deposit: $35 USDC on Polygon + $1–2 POL gas
            </div>
          </div>

          <div style={{ background: "#10141b", border: "1px solid #1d2630", borderRadius: 8, padding: 16 }}>
            <div style={{ color: "#39ff14", fontSize: 12, fontWeight: "bold", marginBottom: 10, textTransform: "uppercase" }}>Paper Venue</div>
            <div style={{ color: "#c8d2dc", fontSize: 12, lineHeight: 1.8 }}>
              Status: <span style={{ color: "#39ff14" }}>ACTIVE</span><br/>
              Markets: 5 synthetic (BTC/ETH/SOL/XRP/DOGE 15M)<br/>
              Prices: fed from real Kalshi /markets/[ticker] mids<br/>
              Spread: 2¢ · Depth: 100 contracts · Fill prob: 85%<br/>
              Purpose: strategy validation when live books are dead
            </div>
          </div>
        </div>

        {/* WHALE + SETTLE ALERTS */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
          <div style={{ background: "#10141b", border: "1px solid #1d2630", borderRadius: 8, padding: 14 }}>
            <div style={{ color: "#FF9000", fontSize: 11, fontWeight: "bold", marginBottom: 8, textTransform: "uppercase" }}>Whale Signals (≥$1k)</div>
            {whale?.signals?.slice(-5).reverse().map((sig, i) => (
              <div key={i} style={{ color: "#c8d2dc", fontSize: 10, marginBottom: 4, fontFamily: "monospace", wordBreak: "break-all" }}>
                {sig.slice(0, 120)}
              </div>
            )) || <div style={{ color: "#6b7785", fontSize: 11 }}>No whale signals yet</div>}
          </div>
          <div style={{ background: "#10141b", border: "1px solid #1d2630", borderRadius: 8, padding: 14 }}>
            <div style={{ color: "#FF9000", fontSize: 11, fontWeight: "bold", marginBottom: 8, textTransform: "uppercase" }}>Settlement Watch</div>
            {settles?.alerts?.slice(-5).reverse().map((a, i) => (
              <div key={i} style={{ color: "#c8d2dc", fontSize: 10, marginBottom: 4, fontFamily: "monospace" }}>
                {a}
              </div>
            )) || <div style={{ color: "#6b7785", fontSize: 11 }}>No imminent settlements</div>}
          </div>
        </div>
      </Section>

      {/* EVENT-DRIVEN ENGINE */}
      <Section title="EVENT-DRIVEN ENGINE" color="#39ff14">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
          <Card title="Core" body={[
            "trading_engine.py — async event queue + strategy dispatch",
            "Event types: MARKET_TICK, PAPER_TICK, TRADE_FILL, ORDER_UPDATE",
            "Pluggable Strategy base class — drop in new logic without touching core",
            "RiskManager: position caps, cash floor, drawdown guard",
            "WsFeed: WebSocket first, REST fallback — sub-second ticks",
          ]} accent="#39ff14" />
          <Card title="Strategies" body={[
            "PanicFade — buys >10¢ drops when YES bid >20¢",
            "WhaleFollow — follows $1k+ volume spikes + 5¢ price moves",
            "Arb — intra-market YES+NO combined < 99¢",
            "All strategies emit WHALE_SIGNAL or TRADE_FILL events",
            "Cooldown + max-position guards on every strategy",
          ]} accent="#06b6d4" />
          <Card title="Order Router" body={[
            "order_router.py — signed V2 POST/DELETE",
            "Client order ID generation",
            "IoC exits on thin books",
            "Paper venue: synthetic book fed by real Kalshi mids",
            "Routes paper orders when live depth = 0",
          ]} accent="#FF9000" />
          <Card title="Ledger" body={[
            "uuid_orders: all orders with exchange_order_id",
            "uuid_fills: all fills with fee tracking",
            "uuid_positions: live positions with avg price + realized P&L",
            "Phantom reconciliation: clears positions exchange no longer carries",
            "17,386 fills · 24,954 orders · 242¢ realized · 1,881 open contracts",
          ]} accent="#ff10f0" />
        </div>
      </Section>

      {/* GYST UUIDv8 */}
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
          <Card title="Scanners" body={[
            "orderbook_monitor — polls 200 markets/10s",
            "liquidity_hunter — enters only on real bid+ask",
            "volume_watchdog — arms when volume_24h > 0",
            "whale_follower — $1k volume spikes + 5¢ moves",
            "settlement_watcher — alerts on markets closing",
            "panic_fade — buys after >10¢ drops, YES >20¢",
            "arb_scanner — Kalshi intra-market + Polymarket signal",
            "paper_venue — feeds from real Kalshi /markets/[ticker] mids",
          ]} accent="#06b6d4" />
          <Card title="Engine" body={[
            "trading_engine.py — async event queue + strategy dispatch",
            "Strategies: panic_fade, whale_follow, arb",
            "WsFeed: WebSocket first, REST fallback",
            "RiskManager: floor guard, max positions, drawdown",
            "OrderRouter: signed V2 + paper venue fallback",
          ]} accent="#39ff14" />
          <Card title="Execution" body={[
            "mission_control — :8420 Kalshi proxy + V2 auth",
            "Floor guard at /api/order — live orders blocked below $15",
            "IoC exits for thin books — fill or cancel",
            "Paper venue: synthetic book when live depth = 0",
            "MAX_ENTRY_PRICE cap — exits always reachable",
          ]} accent="#ff10f0" />
          <Card title="Monitoring" body={[
            ":8420/api/kalshi/balance — live Kalshi cash",
            ":8420/api/kalshi/positions — event positions",
            ":8420/api/whale/signals — whale volume/price alerts",
            ":8420/api/settlements — settlement alerts",
            ":8420/api/stats — ledger + kill switch",
            "mc_state DB — 60s reconciled truth",
          ]} accent="#FF9000" />
        </div>

        {/* SYSTEM FLOW */}
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
            <text x="100" y="95" textAnchor="middle" fill="#6b7785" fontSize="10">Prices: dollars</text>

            <rect x="610" y="10" width="180" height="200" rx="8" fill="#10141b" stroke="#1d2630" strokeWidth="1"/>
            <text x="700" y="35" textAnchor="middle" fill="#ff10f0" fontSize="12" fontWeight="bold">POLYMARKET</text>
            <text x="700" y="55" textAnchor="middle" fill="#6b7785" fontSize="10">CLOB orderbook</text>
            <text x="700" y="75" textAnchor="middle" fill="#6b7785" fontSize="10">Polygon RPC</text>
            <text x="700" y="95" textAnchor="middle" fill="#6b7785" fontSize="10">py-clob-client</text>

            <rect x="320" y="60" width="160" height="100" rx="8" fill="#10141b" stroke="#FF9000" strokeWidth="2"/>
            <text x="400" y="90" textAnchor="middle" fill="#FF9000" fontSize="12" fontWeight="bold">VENUE ROUTER</text>
            <text x="400" y="110" textAnchor="middle" fill="#6b7785" fontSize="10">depth-based routing</text>
            <text x="400" y="130" textAnchor="middle" fill="#6b7785" fontSize="10">paper fallback when dead</text>

            <line x1="190" y1="110" x2="320" y2="110" stroke="#06b6d4" strokeWidth="2" markerEnd="url(#arrow)"/>
            <line x1="480" y1="110" x2="610" y2="110" stroke="#ff10f0" strokeWidth="2" markerEnd="url(#arrow)"/>

            <rect x="320" y="180" width="160" height="30" rx="4" fill="#10141b" stroke="#39ff14" strokeWidth="1"/>
            <text x="400" y="200" textAnchor="middle" fill="#39ff14" fontSize="10">:8420 + paper venue + event engine</text>

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
          <Card title="How We Trade" body={[
            "1 contract per signal — micro size only",
            "BTC/ETH/SOL/XRP/DOGE 15M momentum + panic fade",
            "Entry: 15–35¢ on live bid+ask, no ghost orders",
            "Exit: +3¢ take / −5¢ stop / IoC at settlement",
            "Paper venue: validate strategy against real Kalshi mids",
            "Cross-venue arb: Kalshi + Polymarket >5¢ divergence",
          ]} accent="#39ff14" />
          <Card title="Honesty Machinery" body={[
            "Exchange truth only: fill_count_fp > 0 = real fill",
            "P&L from /portfolio/positions + settles",
            "Wilson 95% CI, n≥50, lower-CI≥55%",
            "Losses published — 4W/0L +$2.42 early, then market decay",
            "No sugarcoating: always post true state",
          ]} accent="#ffaa55" />
          <Card title="Evidence Gates" body={[
            "PROVEN: n≥50 AND lower-CI≥55% AND exp>0",
            "FORMING: 20≤n<50, CI expanding",
            "DEAD: n≥20 AND lower-CI<50% — lane killed",
            "Paper venue continuously tests exits",
            "Live engines adopt winner automatically",
          ]} accent="#06b6d4" />
          <Card title="Bridge + Savings" body={[
            "Kalshi cash: $57.43 · Portfolio: $337",
            "Polymarket USDC: $0 (unfunded, awaiting deposit)",
            "Bridge coordinator watches both balances",
            "25% of every realized win → protected savings sleeve",
          ]} accent="#FF9000" />
        </div>
      </Section>

      {/* RISK CONTROLS */}
      <Section title="RISK CONTROLS" color="#39ff14">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
          <Control label="CASH FLOOR" value="$15 minimum" desc="Never trade below floor" />
          <Control label="MAX ENTRY" value="1–2 contracts" desc="Micro size only" />
          <Control label="BOOK CHECK" value="bid + ask > 0" desc="No ghost orders" />
          <Control label="EXIT MODE" value="IoC limit" desc="Fill or cancel" />
          <Control label="PRICE SOURCE" value={"/markets/" + "[ticker]"} desc="Only truthful endpoint" />
          <Control label="VOLUME FILTER" value="required" desc="No dead books" />
          <Control label="PAPER FALLBACK" value="real Kalshi mids" desc="Trade when venue is frozen" />
          <Control label="KILL SWITCH" value="file-based" desc="Instant halt of all live firing" />
        </div>
      </Section>

      {/* BUILD ROADMAP */}
      <Section title="BUILD ROADMAP" color="#FF9000">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 16 }}>
          <RoadmapItem phase="1" title="Live Monitoring" status="done" desc="Portfolio, orders, positions on :4242 + :8420" />
          <RoadmapItem phase="2" title="Liquidity Scanners" status="done" desc="8 daemons: orderbook, whale, settle, panic fade, arb, paper" />
          <RoadmapItem phase="3" title="BTC Paper Test" status="done" desc="/btc dashboard with live spot P&L" />
          <RoadmapItem phase="4" title="Event-Driven Engine" status="done" desc="trading_engine.py + strategies + WS feed + paper venue" />
          <RoadmapItem phase="5" title="Multi-Venue Router" status="done" desc="Kalshi + Polymarket + paper venue routing" />
          <RoadmapItem phase="6" title="Paper Execution" status="active" desc="Trading on paper venue fed by real Kalshi mids" />
          <RoadmapItem phase="7" title="Live Trading" status="pending" desc="Armed, waiting for executable liquidity on Kalshi or Polymarket funding" />
          <RoadmapItem phase="8" title="Profit Scaling" status="pending" desc="Size up after 60%+ win rate on live closes" />
        </div>
      </Section>

      {/* LIVE SYSTEM STATUS */}
      <Section title="LIVE SYSTEM STATUS" color="#06b6d4">
        <div style={{ background: "#10141b", border: "1px solid #1d2630", borderRadius: 8, padding: 16 }}>
          <pre style={{ color: "#c8d2dc", fontSize: 12, margin: 0, whiteSpace: "pre-wrap" }}>
{JSON.stringify({
  bank: {
    cash: `$${cash}`,
    portfolio: `$${portfolio}`,
    positions: positions_count,
    open_orders: open_orders,
    ledger_pnl_cents: ledger.realized_pnl_cents || 0,
  },
  ledger: {
    orders: ledger.orders || 0,
    fills: ledger.fills || 0,
    open_contracts: ledger.open_contracts || 0,
  },
  kill_switch: kill,
  api_keys: keys,
  corpus_online: !!stats?.corpus?.online,
  venues: {
    kalshi: { cash, portfolio, positions: positions_count, status: "price truth, no depth" },
    polymarket: { wallet: "0xbC66…Dd40", usdc: 0, status: "SIGNAL ONLY" },
    paper: { status: "ACTIVE", markets: 5, source: "real Kalshi mids" },
  },
  dashboards: {
    local: "http://localhost:4242",
    mission_control: "http://localhost:8420",
    info: "https://info.somacosf.com/info",
    grind: "https://grind.somacosf.com",
    btc: "https://btc.somacosf.com",
  },
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
  const statusColor = status === "done" ? "#39ff14" : status === "active" ? "#FF9000" : status === "scaffold" ? "#ffaa55" : "#6b7785";
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
