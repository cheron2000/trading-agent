# Quick Start Guide — AI Trading OS v1.1.0

Get your trading system running in 5 minutes! 🚀

---

## Prerequisites

- ✅ Python 3.11 or higher
- ✅ Windows (current setup)
- ✅ Ollama installed locally OR Groq API key (for ATLAS strategy)

---

## Installation

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) Install dev tools for testing
pip install -r requirements-dev.txt
```

---

## Configuration (keys.env)

Create or edit `keys.env` in the project root:

```bash
# === REQUIRED for ATLAS Strategy ===
# Option 1: Cloud LLM (Groq) - Fast, requires API key
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# Option 2: Local LLM (Ollama) - Free, slower
OLLAMA_MODEL=llama3.1:8b
OLLAMA_HOST=http://localhost:11434

# === OPTIONAL: Telegram Notifications ===
# Get these from @BotFather (see TELEGRAM_SETUP.md)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=987654321

# === OPTIONAL: Alpaca Broker (Paper Trading) ===
# Get from https://alpaca.markets (see ALPACA_SETUP.md)
ALPACA_API_KEY=PKxxxxxxxxxxxxxxxx
ALPACA_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# === OPTIONAL: News Data ===
FINNHUB_API_KEY=your_finnhub_key
AV_KEYS=key1,key2,key3  # Alpha Vantage keys (comma-separated)
```

---

## Running the System

### 1️⃣ Basic Run (Paper Trading, No Notifications)

```bash
# 30-minute session with ATLAS strategy
py -3 run_hour.py --minutes 30
```

**What happens:**
- Uses ATLAS strategy (tries Groq → falls back to Ollama)
- Trades 6 crypto assets (2 per cycle, round-robin)
- In-memory paper fills (no broker)
- Web dashboard at http://127.0.0.1:5000
- Console output only

---

### 2️⃣ With Telegram Notifications

**First time:** Follow `TELEGRAM_SETUP.md` to create your bot (5 minutes)

```bash
py -3 run_hour.py --telegram --minutes 60
```

**You'll get:**
- ✅ Trade fill alerts on your phone
- 🤖 AI decision notifications
- 📊 Session summary when done
- `/status`, `/positions`, `/pnl`, `/stop` commands

---

### 3️⃣ With Alpaca Paper Trading

**First time:** Sign up at https://alpaca.markets and get paper API keys

```bash
py -3 run_hour.py --alpaca --minutes 120
```

**You'll get:**
- Real broker API integration (paper mode)
- Actual order submission and fill polling
- 2% capital limit + 10% drawdown stop
- Position tracking from broker

---

### 4️⃣ Full Setup (Everything Enabled)

```bash
py -3 run_hour.py --strategy ATLAS --telegram --alpaca --minutes 180
```

**Features:**
- ATLAS 6-step regime-gated strategy
- Groq cloud LLM (or Ollama fallback)
- Telegram alerts to your phone
- Alpaca paper broker fills
- Web dashboard live updates
- All risk controls active

---

## Command Line Options

```bash
py -3 run_hour.py [OPTIONS]

Options:
  --minutes N         Trading duration in minutes (default: 120)
  --capital N         Starting capital in USD (default: 200.0)
  --strategy NAME     Strategy: ATLAS, GROQ-LLM, OLLAMA, SIMPLE-RULE (default: ATLAS)
  --telegram          Enable Telegram notifications
  --alpaca            Use Alpaca broker (paper mode)
```

---

## Understanding the Output

### Console Output

```
[Cycle 1] 10:15:23 — 119m 45s remaining | strategy=ATLAS | symbols=BTC-USD, ETH-USD
  [BTC-USD] Fetching price...
  [BTC-USD] Price: $62500.00
  [BTC-USD] Asking ATLAS...
  [BTC-USD] Decision: BUY (confidence=0.85)
  BUY BTC-USD   qty=0.0032 @ $62500.00
```

### Web Dashboard (http://127.0.0.1:5000)

- **Portfolio Value:** Live updates every cycle
- **Positions:** Open trades with P&L
- **Recent Trades:** Last 10 fills
- **Kill Switch:** Emergency stop button
- **Strategy Swap:** Change strategy mid-session

---

## Current Symbol List (v1.1.0)

**Crypto-only (24/7 trading):**
- BTC-USD (Bitcoin)
- ETH-USD (Ethereum)
- SOL-USD (Solana)
- AVAX-USD (Avalanche)
- MATIC-USD (Polygon)
- LINK-USD (Chainlink)

**Processing:** 2 symbols per cycle (round-robin for faster Ollama execution)

---

## Troubleshooting

### "ImportError: No module named ..."
**Fix:** `pip install -r requirements.txt`

### "FileNotFoundError: keys.env"
**Fix:** Create `keys.env` in project root (see Configuration section above)

### "WARNING: Telegram disabled — ValueError"
**Fix:** Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to keys.env

### ATLAS strategy is slow
**Options:**
1. Use Groq cloud LLM (faster): Add `GROQ_API_KEY` to keys.env
2. Switch to simple rules: `--strategy SIMPLE-RULE`
3. Reduce symbols: Edit `SYMBOLS` list in `run_hour.py`

### Dashboard not loading
**Fix:**
1. Check console for "Dashboard running at: http://127.0.0.1:5000"
2. Open browser to http://127.0.0.1:5000 (not https)
3. Port 5000 might be in use — check for other Flask apps

---

## Next Steps

1. **First run:** Start with basic paper trading (no flags)
2. **Add Telegram:** Follow `TELEGRAM_SETUP.md` → run with `--telegram`
3. **Try Alpaca:** Sign up at alpaca.markets → run with `--alpaca`
4. **Optimize:** Tune `_SYMBOLS_PER_CYCLE` or strategy parameters

---

## File Structure

```
keys.env                    ← Your credentials (never commit!)
run_hour.py                 ← Main entry point
run_simulation.py           ← Batch simulation runner

src/
├── intelligence/strategies/
│   ├── atlas_strategy.py   ← 6-step ATLAS system
│   ├── ollama_strategy.py  ← Local LLM strategy
│   └── rule_based.py       ← Simple technical rules
├── execution/broker/
│   └── alpaca_order_manager.py  ← Live broker integration
├── dashboard/
│   ├── web/                ← Flask dashboard
│   └── telegram/           ← Telegram bot
└── data/providers/
    └── yfinance_provider.py ← Live market data

data_store/live/            ← Trade journals (auto-created)
```

---

## Safety Reminders

⚠️ **This is paper trading software**
- No real money is at risk (unless you enable live trading)
- Always run 30 days of paper validation before considering live capital
- See `TEST_DEBT.md` for test coverage status

⚠️ **Live trading gate**
- `--alpaca` runs in paper mode by default
- Live mode requires explicit `paper_validation_complete=True` flag in code
- Never skip the 30-day validation period

---

## Support Resources

- **Telegram Setup:** `TELEGRAM_SETUP.md`
- **Alpaca Setup:** `ALPACA_SETUP.md` (coming soon)
- **Architecture:** `ARCHITECTURE.md`
- **Features:** `FEATURES.md`
- **Test Debt:** `TEST_DEBT.md`
- **Optimization:** `OPTIMIZATION_UPDATE.md`

---

## Example Session

```bash
# 1. Basic 30-minute test
py -3 run_hour.py --minutes 30

# 2. Add Telegram
py -3 run_hour.py --telegram --minutes 60

# 3. Full production setup
py -3 run_hour.py --strategy ATLAS --telegram --alpaca --minutes 180
```

**Expected output:**
- Console: Cycle-by-cycle decisions and fills
- Web: http://127.0.0.1:5000 live dashboard
- Phone: Telegram alerts for every trade

---

**Ready to trade!** 🚀

Start with: `py -3 run_hour.py --minutes 30`
