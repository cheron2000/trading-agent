#!/bin/bash
# =============================================================================
# AI Trading OS — EC2 Bootstrap Script
# =============================================================================
# Run once on a fresh Ubuntu 22.04 t2.micro / t3.micro instance:
#
#   chmod +x setup.sh && ./setup.sh
#
# After setup, copy your keys.env to the server:
#   scp -i your-key.pem keys.env ubuntu@<EC2-IP>:~/trading/keys.env
#
# Then start the bot:
#   cd ~/trading && ./start.sh
# =============================================================================

set -e  # Exit on any error

echo "============================================================"
echo "  AI Trading OS — EC2 Setup"
echo "============================================================"

# --- 1. System update ---
echo "[1/7] Updating system packages..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq

# --- 2. Install Python 3.11 ---
echo "[2/7] Installing Python 3.11..."
sudo apt-get install -y -qq python3.11 python3.11-venv python3.11-dev python3-pip

# --- 3. Install Tor daemon ---
echo "[3/7] Installing Tor daemon..."
sudo apt-get install -y -qq tor

# Configure Tor control port with no password (localhost only)
sudo bash -c 'cat >> /etc/tor/torrc << EOF

# AI Trading OS — control port config
ControlPort 9051
CookieAuthentication 0
EOF'

sudo systemctl enable tor
sudo systemctl restart tor
echo "  Tor daemon started on port 9050 (SOCKS) / 9051 (control)"

# --- 4. Clone repo ---
echo "[4/7] Cloning repository..."
cd ~
if [ -d "trading" ]; then
    echo "  Directory ~/trading already exists — pulling latest..."
    cd trading && git pull
else
    git clone https://github.com/cheron2000/trading-agent trading
    cd trading
fi

# --- 5. Python virtual environment + dependencies ---
echo "[5/7] Setting up Python virtual environment..."
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  Dependencies installed."

# --- 6. Create required directories ---
echo "[6/7] Creating data directories..."
mkdir -p data_store/live
mkdir -p data_store/fixtures
mkdir -p logs

# --- 7. Write start/stop scripts ---
echo "[7/7] Writing start.sh and stop.sh..."

cat > ~/trading/start.sh << 'STARTSCRIPT'
#!/bin/bash
# Start the AI Trading OS in a detached tmux session
cd ~/trading
source .venv/bin/activate

# Set Tor ports for Linux tor daemon
export TOR_SOCKS_PORT=9050
export TOR_CONTROL_PORT=9051

# Kill any existing session
tmux kill-session -t trading 2>/dev/null || true

# Start in new tmux session
tmux new-session -d -s trading \
    "python3.11 run_hour.py --minutes 1440 --capital 10000 2>&1 | tee logs/trading-$(date +%Y%m%d-%H%M).log"

echo "Trading bot started in tmux session 'trading'."
echo "  View live:  tmux attach -t trading"
echo "  Dashboard:  http://$(curl -s ifconfig.me):5000"
echo "  Stop:       ./stop.sh"
STARTSCRIPT

cat > ~/trading/stop.sh << 'STOPSCRIPT'
#!/bin/bash
tmux kill-session -t trading 2>/dev/null && echo "Trading bot stopped." || echo "No active session found."
STOPSCRIPT

chmod +x ~/trading/start.sh ~/trading/stop.sh

# --- Done ---
echo ""
echo "============================================================"
echo "  Setup complete!"
echo "============================================================"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Copy your keys.env to the server:"
echo "     scp -i your-key.pem keys.env ubuntu@<EC2-IP>:~/trading/keys.env"
echo ""
echo "  2. Start the trading bot:"
echo "     cd ~/trading && ./start.sh"
echo ""
echo "  3. View live output:"
echo "     tmux attach -t trading"
echo ""
echo "  4. Open dashboard in browser:"
echo "     http://<EC2-IP>:5000"
echo "     (Make sure port 5000 is open in your EC2 Security Group)"
echo ""
echo "  Tor daemon: running on 9050/9051 (auto-starts on reboot)"
echo "============================================================"
