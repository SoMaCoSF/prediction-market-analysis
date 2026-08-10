// file_id: SOM-TS-XXXX-v1.0.0 name: info/cycle.js description: Live daemon cycle tracker API
/** pages/api/info/cycle.js — live scanner/daemon cycle state for the info page. */
export default async function handler(req, res) {
  try {
    const fs = require("fs");
    const path = require("path");
    const root = path.join(process.cwd(), "..", "logs");

    const daemons = [
      { id: "orderbook_monitor", file: "orderbook_monitor.out", label: "Orderbook Monitor", color: "#06b6d4", watch: "Polls 200 markets/10s for real bid+ask depth. This is the earliest liquidity signal — it catches a moving book before volume ticks." },
      { id: "liquidity_hunter", file: "liquidity_hunter.out", label: "Liquidity Hunter", color: "#39ff14", watch: "Scans for executable depth and enters only when both bid AND ask exist with size. Prevents ghost orders on fake/stale prices." },
      { id: "volume_watchdog", file: "volume_watchdog.out", label: "Volume Watchdog", color: "#FF9000", watch: "Polls /markets every 60s. Arms the fleet when ANY market shows volume_24h > 0. The slowest but most reliable liquidity confirmation." },
      { id: "btc_paper_engine", file: "btc_paper_engine.out", label: "BTC Paper Engine", color: "#ff10f0", watch: "Runs BTC short simulation against live spot. Proves exit math and P&L logic with zero capital risk before live deployment." },
      { id: "mission_control", file: "mission_control.out", label: "Mission Control", color: "#c8d2dc", watch: ":8420 Kalshi proxy. Wraps V2 auth, floor guard, order routing. Source of truth for live balance/positions/orders." },
      { id: "server_view", file: "server_view.out", label: "Server View", color: "#6b7785", watch: ":4242 dashboard. Serves /api/portfolio + /api/venue_health. Public visibility layer for bankroll and venue state." },
    ];

    const now = Date.now();
    const result = daemons.map(d => {
      const logPath = path.join(root, d.file);
      let lastLine = "";
      let lastTs = null;
      let status = "UNKNOWN";

      try {
        if (fs.existsSync(logPath)) {
          const content = fs.readFileSync(logPath, "utf-8");
          const lines = content.split(/\r?\n/).filter(Boolean);
          if (lines.length) {
            lastLine = lines[lines.length - 1];
            // Try to extract timestamp from line
            const tsMatch = lastLine.match(/\[([^\]]+)\]/);
            if (tsMatch) {
              lastTs = tsMatch[1];
            }
            // Determine status from content
            const lower = lastLine.toLowerCase();
            if (lower.includes("starting") || lower.includes("armed") || lower.includes("running")) {
              status = "RUNNING";
            } else if (lower.includes("stopped") || lower.includes("shutting down") || lower.includes("exit")) {
              status = "STOPPED";
            } else if (lower.includes("error") || lower.includes("err") || lower.includes("traceback")) {
              status = "ERROR";
            } else if (lower.includes("no liquidity") || lower.includes("no volume") || lower.includes("sleeping")) {
              status = "SCANNING";
            } else {
              status = "ACTIVE";
            }
          }
        }
      } catch (e) {
        status = "ERROR";
        lastLine = String(e.message);
      }

      return {
        id: d.id,
        label: d.label,
        color: d.color,
        status,
        last_line: lastLine.slice(0, 120),
        last_ts: lastTs,
        watch: d.watch,
        age_seconds: lastTs ? Math.floor((now - new Date(lastTs).getTime()) / 1000) : null,
      };
    });

    res.setHeader("Cache-Control", "no-store");
    res.status(200).json({
      generated_at: new Date().toISOString(),
      daemons: result,
      summary: {
        total: result.length,
        running: result.filter(d => d.status === "RUNNING" || d.status === "SCANNING" || d.status === "ACTIVE").length,
        stopped: result.filter(d => d.status === "STOPPED").length,
        errors: result.filter(d => d.status === "ERROR").length,
      },
    });
  } catch (e) {
    res.status(200).json({ generated_at: new Date().toISOString(), daemons: [], summary: { total: 0, running: 0, stopped: 0, errors: 1 }, error: String(e.message) });
  }
}
