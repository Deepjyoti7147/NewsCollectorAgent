#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# deploy/setup_vm.sh
# Run once on a fresh Ubuntu 22.04 / Debian 12 VM to set up the collector.
# Usage: bash setup_vm.sh
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="/opt/news-collector"
APP_USER="newscollector"

echo "==> Installing system packages"
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3.12-dev \
    libpq-dev gcc \
    git curl ca-certificates

echo "==> Creating app user"
id "$APP_USER" &>/dev/null || useradd -r -s /sbin/nologin -d "$APP_DIR" "$APP_USER"

echo "==> Creating app directory"
mkdir -p "$APP_DIR"
chown "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> Cloning / pulling latest code"
if [ -d "$APP_DIR/.git" ]; then
    sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
else
    sudo -u "$APP_USER" git clone https://github.com/Deepjyoti7147/NewsCollectorAgent.git "$APP_DIR"
fi

echo "==> Creating Python virtual environment"
sudo -u "$APP_USER" python3.12 -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install --no-cache-dir -r "$APP_DIR/requirements.txt"

echo "==> Installing systemd service"
cp "$APP_DIR/deploy/news-collector.service" /etc/systemd/system/news-collector.service
systemctl daemon-reload
systemctl enable news-collector

echo ""
echo "Done! Next steps:"
echo "  1. Copy .env.example to $APP_DIR/.env and fill in your DB credentials."
echo "  2. sudo systemctl start news-collector"
echo "  3. sudo journalctl -u news-collector -f   # tail logs"
