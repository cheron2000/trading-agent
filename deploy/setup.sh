#!/bin/bash
# =============================================================================
# AI Trading OS — EC2 Bootstrap Script
# Run once on a fresh Ubuntu 22.04 EC2 instance (t3.micro or larger)
#
# Usage:
#   chmod +x setup.sh
#   sudo bash setup.sh
# =============================================================================
set -euo pipefail

PROJECT_DIR="/opt/ai-trading-os"
SERVICE_USER="trading"
PYTHON_VERSION="3.11"

echo ""
echo "============================================================"
echo "  AI Trading OS — EC2 Setup"
echo "============================================================"

# --- 1. System updates ---
echo "[1/8] Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq

# --- 2. Install Python 3.11 ---
echo "[2/8] Installing Python ${PYTHON_VERSION}..."
apt-get install -y -qq \
    python3.11 \
    python3.11-venv \
    python3-pip \
    git \
    curl \
    wget \
    screen \
    htop

# --- 3. Install Tor (optional fallback for Yahoo Finance) ---
echo "[3/8] Installing Tor daemon..."
apt-get install -y -qq tor
systemctl enable tor
systemctl start tor
echo "  Tor installed and running on 127.0.0.1:9050"

# --- 4. Create service user ---
echo "[4/8] Creating service user '${SERVICE_USER}'..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -m -s /bin/bash "$SERVICE_USER"
fi

# --- 5. Clone / copy project ---
echo "[5/8] Setting up project directory at ${PROJECT_DIR}..."
if [ ! -d "$PROJECT_DIR" ]; then
    mkdir -p "$PROJECT_DIR"
fi
chown -R "$SERVICE_USER":"$SERVICE_USER" "$PROJECT_DIR"
echo "  Project directory ready: ${PROJECT_DIR}"
echo "  → Upload your code: scp -r ./ ec2-user@YOUR_IP:${PROJECT_DIR}/"
echo "  → Or git clone:     git clone YOUR_REPO ${PROJECT_DIR}"

# --- 6. Create Python venv ---
echo "[6/8] Creating Python virtual environment..."
sudo -u "$SERVICE_USER" python3.11 -m venv "${PROJECT_DIR}/.venv"
echo "  Venv created at ${PROJECT_DIR}/.venv"

# --- 7. Install systemd service ---
echo "[7/8] Installing systemd service..."
cat > /etc/systemd/system/ai-trading.service << 'EOF'
[Unit]
Description=AI Trading OS — Live Paper Trading
After=network-online.target tor.service
Wants=network-online.target

[Service]
Type=simple
User=trading
WorkingDirectory=/opt/ai-trading-os
Environment="PYTHONPATH=/opt/ai-trading-os/src"
Environment="PYTHONUNBUFFERED=1"
ExecStart=/opt/ai-trading-os/.venv/bin/python run_hour.py --minutes 1440
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ai-trading

# Resource limits
MemoryMax=512M
CPUQuota=50%

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
echo "  Service installed: ai-trading.service"

# --- 8. Log rotation ---
echo "[8/8] Setting up log rotation..."
cat > /etc/logrotate.d/ai-trading << 'EOF'
/var/log/ai-trading/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 trading trading
}
EOF
mkdir -p /var/log/ai-trading
chown trading:trading /var/log/ai-trading

echo ""
echo "============================================================"
echo "  Setup complete!"
echo "============================================================"
echo ""
echo "  NEXT STEPS:"
echo ""
echo "  1. Upload your project files to ${PROJECT_DIR}/"
echo "     scp -r * ec2-user@YOUR_IP:${PROJECT_DIR}/"
echo ""
echo "  2. Add your API keys:"
echo "     sudo nano ${PROJECT_DIR}/keys.env"
echo "     → AV_KEYS=KEY1,KEY2,KEY3,..."
echo ""
echo "  3. Install Python dependencies:"
echo "     sudo -u trading ${PROJECT_DIR}/.venv/bin/pip install -r ${PROJECT_DIR}/requirements.txt"
echo ""
echo "  4. Start the trading service:"
echo "     sudo systemctl start ai-trading"
echo "     sudo systemctl enable ai-trading"
echo ""
echo "  5. Watch live logs:"
echo "     sudo journalctl -u ai-trading -f"
echo ""
echo "  6. Check status:"
echo "     sudo systemctl status ai-trading"
echo ""
