# file_id: SOM-SH-0977-v1.0.0 name: scripts/provision_vps.sh description: Provision a Linux VPS (Hetzner/omen-02-Linux) for the SoMaCo fleet — uv venv, deps, systemd supervisor unit; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [provision, vps, systemd, deploy] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
#!/usr/bin/env bash
# provision_vps.sh — one-shot fleet setup on a fresh Ubuntu/Debian box.
# Usage: git clone <private-repo> && cd prediction-market-analysis && bash scripts/provision_vps.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== 1. system deps =="
sudo apt-get update -qq
sudo apt-get install -y -qq python3.11 python3.11-venv curl git

echo "== 2. uv =="
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

echo "== 3. venv + python deps =="
uv venv .venv311 --python 3.11
.venv311/bin/python -m ensurepip --upgrade 2>/dev/null || true
if [ -f scripts/_deps_core.txt ]; then
  uv pip install --python .venv311/bin/python -r scripts/_deps_core.txt
else
  uv pip install --python .venv311/bin/python httpx cryptography psycopg2-binary python-dotenv fastapi uvicorn pytest ruff
fi

echo "== 4. secrets =="
if [ ! -f .env ] || [ ! -f .kalshi_key.pem ]; then
  echo "!! .env and .kalshi_key.pem must be restored from the password manager BEFORE the fleet can trade."
fi

echo "== 5. systemd unit =="
sudo tee /etc/systemd/system/somaco-fleet.service >/dev/null <<UNIT
[Unit]
Description=SoMaCo fleet supervisor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
Environment=PYTHONPATH=
ExecStart=$ROOT/.venv311/bin/python $ROOT/scripts/supervisor.py
Restart=always
RestartSec=30
User=$USER

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable somaco-fleet
echo "== done =="
echo "Start:  sudo systemctl start somaco-fleet"
echo "Status: systemctl status somaco-fleet | head"
echo "Logs:   tail -f $ROOT/logs/*.out.log"
