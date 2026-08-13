#!/usr/bin/env python3
"""Standalone positions dashboard with manual exit."""
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "kalshi_balance.json"
EXIT_SCRIPT = ROOT / "scripts" / "positions_exit.py"
PYTHON = Path(__file__).resolve().parent / ".venv311" / "Scripts" / "python.exe"


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/positions":
            try:
                data = json.loads(DATA.read_text())
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode())
            return

        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/exit":
            try:
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                payload = json.loads(body)
                ticker = payload.get("ticker")
                count = payload.get("count", "1")
                price = payload.get("price", "0.01")
                if not ticker:
                    raise ValueError("missing ticker")

                # Run exit script in background
                def run_exit():
                    env = os.environ.copy()
                    env["EXIT_TICKER"] = ticker
                    env["EXIT_COUNT"] = str(count)
                    env["EXIT_PRICE"] = str(price)
                    subprocess.run([str(PYTHON), str(EXIT_SCRIPT)], env=env, cwd=str(ROOT))

                threading.Thread(target=run_exit, daemon=True).start()
                self.send_response(202)
                self.end_headers()
                self.wfile.write(json.dumps({"status": "exit_started", "ticker": ticker}).encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

        self.send_response(404)
        self.end_headers()


DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Positions Dashboard</title>
  <style>
    body { font-family: system-ui; margin: 24px; background: #0b0c10; color: #c5c6c7; }
    h1 { color: #66fcf1; }
    .card { background: #1f2833; padding: 16px; border-radius: 8px; margin-bottom: 16px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 8px; text-align: left; border-bottom: 1px solid #2d333b; }
    th { color: #66fcf1; }
    .btn { background: #45a29e; color: white; border: none; padding: 6px 10px; border-radius: 4px; cursor: pointer; }
    .btn:hover { background: #66fcf1; color: #0b0c10; }
    .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; }
    .metric { background: #2d333b; padding: 12px; border-radius: 6px; text-align: center; }
    .metric .value { font-size: 20px; color: #66fcf1; }
  </style>
</head>
<body>
  <h1>Kalshi Positions</h1>
  <div class="metrics" id="metrics"></div>
  <div class="card">
    <h2>Positions</h2>
    <table>
      <thead>
        <tr><th>Ticker</th><th>Count</th><th>Value</th><th>P&L</th><th>Action</th></tr>
      </thead>
      <tbody id="positions"></tbody>
    </table>
  </div>

  <script>
    async function load() {
      const res = await fetch('/api/positions');
      const data = await res.json();
      const metrics = document.getElementById('metrics');
      metrics.innerHTML = `
        <div class="metric"><div class="value">$${data.balance.toFixed(2)}</div><div>Cash</div></div>
        <div class="metric"><div class="value">${data.positions_count}</div><div>Positions</div></div>
      `;

      const tbody = document.getElementById('positions');
      tbody.innerHTML = '';
      for (const p of data.positions || []) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${p.ticker}</td>
          <td>${p.count}</td>
          <td>$${Number(p.value || 0).toFixed(2)}</td>
          <td>${Number(p.pnl || 0).toFixed(2)}</td>
          <td><button class="btn" onclick="exitPosition('${p.ticker}', ${p.count}, '0.01')">Exit 1 @ 0.01</button></td>
        `;
        tbody.appendChild(tr);
      }
    }

    async function exitPosition(ticker, count, price) {
      await fetch('/api/exit', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ ticker, count: Math.min(1, count), price })
      });
      setTimeout(load, 1500);
    }

    load();
    setInterval(load, 10000);
  </script>
</body>
</html>
"""


def main():
    port = 8123
    server = HTTPServer(("127.0.0.1", port), DashboardHandler)
    print(f"Dashboard running at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
