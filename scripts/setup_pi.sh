#!/usr/bin/env bash
# One-time setup on the Pi (Raspberry Pi OS with desktop). Run from the repo folder:
#   bash scripts/setup_pi.sh
# Safe to re-run. Never prints or stores your API key anywhere except .env (git-ignored).
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"

echo ">>> System packages"
sudo apt update
sudo apt install -y python3-venv python3-pip git rpicam-apps curl
command -v chromium >/dev/null || command -v chromium-browser >/dev/null || sudo apt install -y chromium

echo ">>> Python venv"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo ">>> Serial port access (takes effect after reboot)"
sudo usermod -aG dialout "$USER"

echo ">>> Private files (git-ignored)"
[ -f .env ] || { cp .env.example .env; chmod 600 .env; echo "    created .env  -> add PERPLEXITY_API_KEY with: nano .env"; }
[ -f guests.json ] || { cp guests.example.json guests.json; echo "    created guests.json -> edit names/allergies"; }
[ -f machine.json ] || { cp machine.example.json machine.json; echo "    created machine.json -> measure pie_x / pie_y / z_surface"; }

echo ">>> PumpkinPi server as a service (starts at boot, localhost only)"
sudo tee /etc/systemd/system/pumpkinpi.service >/dev/null <<UNIT
[Unit]
Description=PumpkinPi touchscreen server
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$REPO
EnvironmentFile=$REPO/.env
ExecStart=$REPO/.venv/bin/python -m pumpkinpi.server
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable pumpkinpi.service

echo ">>> Full-screen touchscreen UI at login (labwc)"
mkdir -p "$HOME/.config/labwc"
touch "$HOME/.config/labwc/autostart"
grep -q "scripts/kiosk.sh" "$HOME/.config/labwc/autostart" || echo "$REPO/scripts/kiosk.sh &" >> "$HOME/.config/labwc/autostart"
chmod +x scripts/kiosk.sh

echo
echo "Done. Next:"
echo "  1. nano .env           # paste PERPLEXITY_API_KEY=..."
echo "  2. Rotate the screen: Preferences > Control Centre > Screens > DSI-1 > Orientation (landscape)"
echo "  3. sudo reboot"
echo "  4. After reboot:  .venv/bin/python -m pumpkinpi.doctor"
