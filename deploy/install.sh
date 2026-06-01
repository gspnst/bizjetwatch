#!/usr/bin/env bash
# One-shot installer for a Raspberry Pi (Debian/Raspberry Pi OS).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

echo "==> creating virtualenv"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip >/dev/null
./.venv/bin/pip install -r requirements.txt

echo "==> installing systemd service"
SERVICE=/etc/systemd/system/bizjet-watch.service
sed "s#/home/pi/bizjet-watch#${HERE}#g; s#User=pi#User=$(whoami)#g" deploy/bizjet-watch.service | sudo tee "$SERVICE" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now bizjet-watch

IP=$(hostname -I | awk '{print $1}')
echo "==> done. Open  http://${IP}:8000/"
echo "    First start downloads the aircraft database once (watch: journalctl -u bizjet-watch -f)"
