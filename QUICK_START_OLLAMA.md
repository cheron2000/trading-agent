# Quick Start Guide — Ollama Strategy (Local LLM)

**Date:** August 6, 2026  
**Purpose:** Get trading quickly without any API keys

---

## Prerequisites

### 1. Install Ollama

**Windows:**
```bash
# Download from: https://ollama.com/download/windows
# Or use winget:
winget install Ollama.Ollama
```

**After installation:**
```bash
# Verify it's running
ollama --version

# Pull the default model (llama3.1:8b)
ollama pull llama3.1:8b
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

---

## Minimal Setup (No API Keys Required)

### Option 1: ATLAS Strategy with Ollama (Recommended)

**Edit `keys.env`:**
```bash
# Ollama (local LLM) - already configured by default
OLLAMA_MODEL=llama3.1:8b
OLLAMA_HOST=http://localhost:11434

# Leave these empty - not needed for Ollama
GROQ_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
```

**Run:**
```bash
py -3 run_hour.py --strategy ATLAS --minutes 30
```

**What happens:**
- ATLAS tries Groq (fails, no key)
- Automatically falls back to Ollama (local, no keys needed)
- Processes 2 symbols per cycle (round-robin)
- Web dashboard at http://127.0.0.1:5000
- Terminal shows all decisions and trades

---

### Option 2: Original Ollama Strategy

**Run:**
```bash
py -3 run_hour.py --strategy OLLAMA --minutes 30
```

**Difference:**
- Uses simpler prompt than ATLAS
- No regime gating or confluence scoring
- Faster but less sophisticated

---

## Expected Performance

### Cycle Timing (2 symbols per cycle)

| Model | Time per Symbol | Cycle Time (2 symbols) |
|-------|----------------|----------------------|
| Ollama (CPU) | 15-25s | ~40-50s |
| Ollama (GPU) | 3-5s | ~10s |
| ATLAS Groq Cloud | 2-4s | ~8s |

**With round-robin optimization:** All cycles complete within 60-second interval ✅

### Coverage

- **Cycle 1:** BTC-USD, ETH-USD
- **Cycle 2:** SOL-USD, AVAX-USD
- **Cycle 3:** MATIC-USD, LINK-USD
- **Cycle 4:** Repeats...

Each symbol evaluated every **3 minutes** (3 cycles).

---

## Monitoring Your Run

### Terminal Output

```
[Cycle 1] 10:15:23 — 29m 45s remaining | strategy=ATLAS | symbols=BTC-USD, ETH-USD
  [BTC-USD] Fetching price...
  [BTC-USD] Price: $65432.10
  [BTC-USD] Asking ATLAS...
  [BTC-USD] Decision: HOLD (confidence=0.45)
  
  [ETH-USD] Fetching price...
  [ETH-USD] Price: $3456.78
  [ETH-USD] Asking ATLAS...
  [ETH-USD] Decision: BUY (confidence=0.72)
  BUY ETH-USD qty=0.5234 @ $3456.78
```

### Web Dashboard

Open http://127.0.0.1:5000 in your browser to see:
- Real-time portfolio value
- Position list with P&L
- Trade history
- Performance metrics (Sharpe, drawdown, win rate)
- Kill switch button

---

## Troubleshooting

### "Connection refused to localhost:11434"

**Problem:** Ollama server not running

**Fix:**
```bash
# Start Ollama service
ollama serve

# In another terminal, verify it's running
ollama list
```

### "Model llama3.1:8b not found"

**Problem:** Model not downloaded

**Fix:**
```bash
ollama pull llama3.1:8b
```

### Cycles taking too long (> 60 seconds)

**Problem:** CPU is slow

**Solutions:**
1. **Use smaller model:**
   ```bash
   ollama pull llama3.2:3b  # Smaller, faster
   ```
   Update `keys.env`:
   ```
   OLLAMA_MODEL=llama3.2:3b
   ```

2. **Process 1 symbol per cycle:**
   Edit `run_hour.py` line ~360:
   ```python
   _SYMBOLS_PER_CYCLE = 1  # Change from 2 to 1
   ```

3. **Use GPU acceleration:**
   - Install CUDA toolkit (NVIDIA GPU)
   - Ollama will auto-detect and use GPU (3-5x faster)

---

## Adding Optional Features Later

### 1. Telegram Notifications

**Setup:** See main README or ask for help  
**Run with:**
```bash
py -3 run_hour.py --strategy ATLAS --telegram --minutes 30
```

### 2. Alpaca Paper Trading

**Setup:** Create free account at https://alpaca.markets  
**Run with:**
```bash
py -3 run_hour.py --strategy ATLAS --alpaca --minutes 30
```

### 3. Groq Cloud LLM (Faster than Ollama)

**Setup:** Get free API key from https://groq.com  
**Add to `keys.env`:**
```bash
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

ATLAS will automatically use Groq instead of Ollama (2-4x faster).

---

## Recommended First Run

**Start simple, add features incrementally:**

### Run 1: Test Ollama (10 minutes)
```bash
py -3 run_hour.py --strategy ATLAS --minutes 10
```
**Goal:** Verify Ollama works and cycles complete on time.

### Run 2: Short Session (30 minutes)
```bash
py -3 run_hour.py --strategy ATLAS --minutes 30
```
**Goal:** See a few complete round-trips (BUY → SELL).

### Run 3: Full Session (2 hours)
```bash
py -3 run_hour.py --strategy ATLAS --minutes 120
```
**Goal:** Collect enough trades for meaningful metrics.

---

## What You'll See

After the session ends, you'll get a report:

```
📊 Session Summary
Total P&L:    +$45.67
Win Rate:     60.0%
Total Trades: 10
Sharpe:       1.2345
Max Drawdown: 2.34%

Recent trades (last 5):
  ETH-USD    SELL  qty=0.5234  @ $3500.00  P&L=$+22.34
  BTC-USD    SELL  qty=0.0123  @ $66000.00 P&L=$+15.45
  ...
```

**Journal saved to:** `data_store/live/journal-live-run-YYYY-MM-DD-HHMM.jsonl`

---

## Summary

✅ **No API keys needed** - Ollama runs 100% locally  
✅ **No Telegram setup** - Skip `--telegram` flag  
✅ **No Alpaca account** - Skip `--alpaca` flag  
✅ **Just run** - `py -3 run_hour.py --strategy ATLAS --minutes 30`

**Start trading in under 5 minutes!** 🚀
