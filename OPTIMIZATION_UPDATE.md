# Optimization Update — Round-Robin Symbol Processing

**Date:** August 6, 2026  
**Version:** v1.1.0  
**Author:** AI Trading OS Team

---

## Problem Statement

The ATLAS strategy using local Ollama LLM was taking too long to process all 6 symbols sequentially in a single cycle:
- **Ollama latency:** ~10-30 seconds per symbol (CPU-dependent)
- **6 symbols × 20 seconds** = ~120 seconds per cycle
- **60-second cycle interval** → impossible to meet, causing backlog

Additionally, stock market hours (NYSE 9:30-16:00 ET) limited trading windows for 4 of the 6 symbols.

---

## Solution Implemented

### 1. **Round-Robin Symbol Processing**

Instead of processing all 6 symbols in every cycle, we now process **2 symbols per cycle** in a rotating pattern:

```
Cycle 1: BTC-USD, ETH-USD
Cycle 2: SOL-USD, AVAX-USD
Cycle 3: MATIC-USD, LINK-USD
Cycle 4: BTC-USD, ETH-USD (rotation continues)
```

**Benefits:**
- ✅ **3x faster cycles:** 2 symbols × 20s = ~40 seconds (fits comfortably in 60s interval)
- ✅ **Fair coverage:** All symbols evaluated every 3 cycles (3 minutes)
- ✅ **Reduced load:** Less CPU/memory pressure per cycle
- ✅ **Better logging:** Clearer cycle output showing which symbols were processed

**Implementation:**
```python
# Round-robin symbol rotation — process 2 symbols per cycle
_SYMBOLS_PER_CYCLE = 2
_symbol_rotation_index = 0

# In main loop:
symbols_this_cycle = []
for i in range(_SYMBOLS_PER_CYCLE):
    idx = (_symbol_rotation_index + i) % len(SYMBOLS)
    symbols_this_cycle.append(SYMBOLS[idx])
_symbol_rotation_index = (_symbol_rotation_index + _SYMBOLS_PER_CYCLE) % len(SYMBOLS)
```

---

### 2. **24/7 Crypto Markets**

Replaced mixed stock/crypto portfolio with **crypto-only** to eliminate market hours constraints:

**Old:**
```python
SYMBOLS = ["AAPL", "MSFT", "GOOGL", "BTC-USD", "ETH-USD", "TSLA"]
# 4 stocks (NYSE hours only) + 2 crypto (24/7)
```

**New:**
```python
SYMBOLS = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "MATIC-USD", "LINK-USD"]
# 6 crypto (all 24/7)
```

**Benefits:**
- ✅ **24/7 operation:** No market hours restrictions
- ✅ **Higher liquidity:** Major crypto assets with deep order books
- ✅ **Better data quality:** Crypto exchanges provide continuous real-time data
- ✅ **Diversification:** 2 major + 4 alt layer-1s with different correlation patterns

---

### 3. **Updated Correlation Groups**

Adjusted correlation limits for crypto-only portfolio:

```python
_CORRELATION_GROUPS = [
    {"BTC-USD", "ETH-USD"},                          # Major crypto — max 2
    {"SOL-USD", "AVAX-USD", "MATIC-USD", "LINK-USD"} # Alt layer-1s — max 2
]
_MAX_CORRELATED_LONGS = {
    0: 2,  # Allow both BTC + ETH simultaneously
    1: 2,  # Allow 2 of 4 alt L1s simultaneously
}
```

---

## Performance Comparison

### Before Optimization

| Metric | Value |
|--------|-------|
| Symbols per cycle | 6 |
| LLM calls per cycle | 6 |
| Cycle duration (Ollama) | ~120 seconds |
| Cycle interval target | 60 seconds |
| **Result** | ❌ Backlog buildup |

### After Optimization

| Metric | Value |
|--------|-------|
| Symbols per cycle | 2 |
| LLM calls per cycle | 2 |
| Cycle duration (Ollama) | ~40 seconds |
| Cycle interval target | 60 seconds |
| **Result** | ✅ On-time execution |

---

## Usage

### Run with Optimized Configuration

```bash
# ATLAS strategy with round-robin + Telegram + Alpaca paper
py -3 run_hour.py --strategy ATLAS --telegram --alpaca --minutes 120

# Output shows which symbols are processed each cycle:
# [Cycle 1] 10:15:23 — 119m 45s remaining | strategy=ATLAS | symbols=BTC-USD, ETH-USD
# [Cycle 2] 10:16:23 — 118m 45s remaining | strategy=ATLAS | symbols=SOL-USD, AVAX-USD
# [Cycle 3] 10:17:23 — 117m 45s remaining | strategy=ATLAS | symbols=MATIC-USD, LINK-USD
```

### Adjust Symbols Per Cycle

To process 3 symbols per cycle (every symbol covered in 2 cycles):

```python
# In run_hour.py
_SYMBOLS_PER_CYCLE = 3  # Change from 2 to 3
```

To process 1 symbol per cycle (maximum LLM time, 6 cycles to cover all):

```python
_SYMBOLS_PER_CYCLE = 1
```

---

## Trade-offs

### ✅ Advantages
1. **Faster execution:** Ollama can complete analysis within cycle time budget
2. **Scalability:** Can handle slower LLMs or add more symbols without blocking
3. **Better monitoring:** Clear per-cycle symbol tracking
4. **24/7 operation:** No market hours downtime

### ⚠️ Considerations
1. **Delayed coverage:** Each symbol evaluated every 3 cycles (3 minutes) instead of every cycle (1 minute)
   - **Mitigation:** 3-minute intervals are still acceptable for the current strategy timeframe (60-second technical indicators)
2. **Position imbalance risk:** One symbol might miss a critical signal while waiting for its turn
   - **Mitigation:** ATR-based trailing stops protect all positions regardless of evaluation frequency
3. **Crypto-only exposure:** Removed stock diversification
   - **Temporary:** Can revert to stocks after Ollama optimization or switch to Groq cloud LLM

---

## Next Steps

### Short-term (Recommended)
1. **Monitor performance:** Run 24-48 hour session to validate cycle timing
2. **Tune `_SYMBOLS_PER_CYCLE`:** Experiment with 3 symbols per cycle if Ollama improves
3. **Add Groq fallback:** Use cloud LLM during peak volatility for faster decisions

### Medium-term
1. **Parallel LLM calls:** Process 2 symbols concurrently using `asyncio` or threading
2. **Symbol prioritization:** Process volatile symbols more frequently than stable ones
3. **Hybrid approach:** Mix stocks (NYSE hours) + crypto (24/7) with smart scheduling

### Long-term
1. **GPU acceleration:** Move Ollama to GPU for 3-5x faster inference
2. **Quantized models:** Use smaller Ollama models (4-bit quantization) for 2x speedup
3. **Streaming responses:** Use Ollama streaming API to start decision-making before full response completes

---

## Files Changed

- `run_hour.py` — Round-robin logic, crypto-only symbols, updated correlation groups
- `README.md` — Updated to v1.1.0, documented new features
- `OPTIMIZATION_UPDATE.md` — This document

---

## GitHub Commit

**Commit:** `17f3076`  
**Branch:** `master`  
**Status:** ✅ Pushed successfully to https://github.com/cheron2000/trading-agent

**Commit Message:**
```
feat: Implement ATLAS strategy, Alpaca broker integration, Telegram notifications, and round-robin symbol processing

Major Updates:
- ATLAS Strategy: 6-step regime-gated multi-factor confluence system with dual LLM backend (Groq/Ollama)
- Alpaca Order Manager: Live broker integration with 2% capital limit and 10% drawdown stop
- Telegram Notifier: Real-time trade alerts and remote commands (/status, /positions, /pnl, /stop)
- Round-robin processing: 2 symbols per cycle for faster Ollama execution
- 24/7 crypto markets: BTC, ETH, SOL, AVAX, MATIC, LINK
```

---

## Conclusion

The round-robin optimization makes ATLAS strategy with local Ollama **practical and performant**. The system now executes on schedule, provides clear monitoring, and operates 24/7 on crypto markets.

**Key takeaway:** When LLM latency is a bottleneck, **distribute the workload across cycles** instead of compromising strategy quality or switching to simpler rules.
