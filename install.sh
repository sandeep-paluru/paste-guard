#!/usr/bin/env bash
# One-command setup:  ./install.sh [--service]
# Creates a virtualenv, installs dependencies, downloads the embedding model
# (about 90 MB, once), builds the index from paste-guard.toml and, with
# --service, installs a systemd service that starts Paste Guard on boot.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
command -v python3 >/dev/null || { echo "python3 (3.10+) is required"; exit 1; }
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r backend/requirements.txt
echo "Building index from paste-guard.toml ..."
./pasteguard reindex
if [ "${1:-}" = "--service" ]; then
  sudo tee /etc/systemd/system/paste-guard.service >/dev/null <<UNIT
[Unit]
Description=Paste Guard backend
After=network.target

[Service]
User=$(id -un)
WorkingDirectory=$ROOT/backend
Environment=PG_CONFIG=$ROOT/paste-guard.toml
Environment=PG_THREADS=1
ExecStart=$ROOT/pasteguard serve
Restart=on-failure
MemoryMax=600M

[Install]
WantedBy=multi-user.target
UNIT
  sudo systemctl daemon-reload && sudo systemctl enable --now paste-guard.service
  echo "Service installed: systemctl status paste-guard"
else
  echo "Start it with: ./pasteguard serve"
fi
echo "Then load extension/ in chrome://extensions (Developer mode, Load unpacked). Admin: http://127.0.0.1:8765/admin"
