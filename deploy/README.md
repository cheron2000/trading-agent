# AI Trading OS — AWS Deployment Guide

Deploy the trading system on AWS EC2 for 24/7 paper trading.

---

## Prerequisites

- AWS account with EC2 access
- Your Alpha Vantage API keys (in `keys.env`)
- SSH client (PuTTY on Windows or built-in terminal)

---

## Step 1 — Launch EC2 Instance

1. Go to **AWS Console → EC2 → Launch Instance**
2. Settings:
   - **Name:** `ai-trading-os`
   - **AMI:** Ubuntu Server 22.04 LTS (free tier eligible)
   - **Instance type:** `t3.micro` (~$8/month) or `t3.small` for more headroom
   - **Key pair:** Create new → download `.pem` file → keep it safe
   - **Security group:** Allow SSH (port 22) from your IP only
   - **Storage:** 20 GB gp3 (default is fine)
3. Click **Launch Instance**
4. Note your **Public IPv4 address**

---

## Step 2 — Connect to EC2

```bash
# On Windows — use PowerShell or Git Bash
chmod 400 your-key.pem
ssh -i your-key.pem ubuntu@YOUR_EC2_IP
```

---

## Step 3 — Run Setup Script

```bash
# Upload setup script
scp -i your-key.pem deploy/setup.sh ubuntu@YOUR_EC2_IP:~/

# SSH in and run it
ssh -i your-key.pem ubuntu@YOUR_EC2_IP
sudo bash setup.sh
```

This installs Python 3.11, Tor, creates the `trading` service user, and registers the systemd service.

---

## Step 4 — Upload Project Files

From your local machine (Windows PowerShell):

```powershell
# Upload entire project (excludes .venv, .git)
scp -i your-key.pem -r `
  src `
  data_store `
  scripts `
  requirements.txt `
  requirements-dev.txt `
  run_hour.py `
  run_simulation.py `
  load_keys.py `
  ubuntu@YOUR_EC2_IP:/opt/ai-trading-os/
```

---

## Step 5 — Add API Keys

```bash
# SSH into EC2
ssh -i your-key.pem ubuntu@YOUR_EC2_IP

# Create keys.env
sudo nano /opt/ai-trading-os/keys.env
```

Add your keys:
```
AV_KEYS=KEY1,KEY2,KEY3,KEY4,KEY5
```

Save and exit (`Ctrl+X → Y → Enter`).

---

## Step 6 — Install Python Dependencies

```bash
sudo -u trading /opt/ai-trading-os/.venv/bin/pip install -r /opt/ai-trading-os/requirements.txt
```

---

## Step 7 — Test Before Going Live

```bash
# Test API keys
cd /opt/ai-trading-os
sudo -u trading .venv/bin/python test_av_key.py

# Run a quick 5-minute test
sudo -u trading PYTHONPATH=src .venv/bin/python run_hour.py --minutes 5
```

---

## Step 8 — Start 24/7 Service

```bash
# Start the service
sudo systemctl start ai-trading

# Enable auto-start on reboot
sudo systemctl enable ai-trading

# Check it's running
sudo systemctl status ai-trading
```

---

## Monitoring

```bash
# Live logs (Ctrl+C to exit)
sudo journalctl -u ai-trading -f

# Last 100 lines
sudo journalctl -u ai-trading -n 100

# Check if running
sudo systemctl status ai-trading

# Stop temporarily
sudo systemctl stop ai-trading

# Restart after code update
sudo systemctl restart ai-trading
```

---

## Updating Code

```bash
# From your local machine — upload changed files
scp -i your-key.pem src/paper_trading/runner.py ubuntu@YOUR_EC2_IP:/opt/ai-trading-os/src/paper_trading/

# On EC2 — restart service to pick up changes
sudo systemctl restart ai-trading
```

---

## Adding More API Keys

```bash
sudo nano /opt/ai-trading-os/keys.env
# Add new keys to AV_KEYS=...
sudo systemctl restart ai-trading
```

---

## Cost Estimate (50 days)

| Resource | Rate | 50-day cost |
|---|---|---|
| t3.micro (on-demand) | ~$0.0104/hr | ~$12.50 |
| EBS 20GB gp3 | ~$0.08/GB/month | ~$2.70 |
| Data transfer out | First 100GB free | $0 |
| **Total** | | **~$15.20** |

Well within $150 Bedrock credits. Note: Bedrock credits apply to AI/ML services — verify EC2 billing separately in your AWS console.

---

## Tor on EC2 (already installed by setup.sh)

Tor runs as a system daemon automatically. No browser needed.

```bash
# Check Tor status
sudo systemctl status tor

# Verify it's listening on port 9050
ss -tlnp | grep 9050
```

To use Tor mode in `run_hour.py`, it's already configured with `use_tor=True`. On EC2 the Tor daemon starts with the instance and stays running permanently.

---

## Architecture on EC2

```
EC2 t3.micro (Ubuntu 22.04)
│
├── systemd: ai-trading.service
│   └── python run_hour.py --minutes 1440  (24h cycle, auto-restarts)
│       ├── AlphaVantageProvider  (primary, key rotation)
│       ├── YFinanceProvider + Tor  (fallback)
│       └── Full 7-layer pipeline
│
├── systemd: tor.service  (always running, port 9050)
│
└── /opt/ai-trading-os/
    ├── keys.env          (your API keys, never committed to git)
    ├── src/              (all 7 layers)
    └── .venv/            (Python dependencies)
```
