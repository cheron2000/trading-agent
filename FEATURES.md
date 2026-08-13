# FEATURES.md — Trading Agent Improvement Roadmap

Track all planned improvements to make the agent profitable.
Each feature has a status, estimated impact, and implementation notes.

---

## Status Legend
- `[ ]` — Not started
- `[/]` — In progress
- `[x]` — Done
- `[-]` — Skipped / Deferred

---

## Feature List

### FEAT-01: RSI Indicator in FeatureEngineer ✅ DONE
**Status:** `[x]`  
**Impact:** ★★★★★  
**File:** `src/data/features/feature_engineer.py`  
**What:** Add RSI-14 (Relative Strength Index) to the computed feature vector.  
RSI < 35 = oversold (potential buy), RSI > 70 = overbought (potential sell).  
**Depends on:** Nothing — pure math from existing price window.

---

### FEAT-02: MACD in FeatureEngineer ✅ DONE
**Status:** `[x]`  
**Impact:** ★★★★★  
**File:** `src/data/features/feature_engineer.py`  
**What:** Add MACD (12-period EMA minus 26-period EMA) and Signal Line (9-period EMA of MACD).  
MACD > Signal = bullish momentum, MACD < Signal = bearish momentum.  
**Depends on:** FEAT-01 (both go in the same FeatureEngineer pass).

---

### FEAT-03: Bollinger Bands in FeatureEngineer ✅ DONE
**Status:** `[x]`  
**Impact:** ★★★☆☆  
**File:** `src/data/features/feature_engineer.py`  
**What:** Add BB upper/lower/mid bands (20-period SMA ± 2 std devs).  
Price near lower band = potential bounce, near upper = potential reversal.  
**Depends on:** FEAT-01.

---

### FEAT-04: Volume Ratio Feature ✅ DONE
**Status:** `[x]`  
**Impact:** ★★★★☆  
**File:** `src/data/features/feature_engineer.py`  
**What:** Add `volume_ratio = current_volume / average_volume`.  
Ratio > 1.5 confirms breakouts; ratio < 0.5 = weak move, ignore signal.  
**Depends on:** FEAT-01.

---

### FEAT-05: Upgrade OllamaStrategy Prompt with New Indicators ✅ DONE
**Status:** `[x]`  
**Impact:** ★★★★★  
**File:** `src/intelligence/strategies/ollama_strategy.py`  
**What:** Rewrite `_build_prompt()` to include RSI, MACD, Bollinger Bands, and volume ratio.  
Give the LLM a specific rule-based framework to follow instead of vague "analyze this".  
**Depends on:** FEAT-01, FEAT-02, FEAT-03, FEAT-04.

---

### FEAT-06: Position Memory in Prompt ✅ DONE
**Status:** `[x]`  
**Impact:** ★★★★☆  
**File:** `src/intelligence/strategies/ollama_strategy.py`, `run_hour.py`  
**What:** Pass current position data (entry price, current P&L%, hold duration) into the LLM prompt.  
The agent should know "I bought AAPL at $180, it's now $185 (+2.8%), held for 3 cycles."  
**Depends on:** FEAT-05.

---

### FEAT-07: Dynamic ATR-Based Stop-Loss ✅ DONE
**Status:** `[x]`  
**Impact:** ★★★★★  
**File:** `run_hour.py`, `src/data/features/feature_engineer.py`  
**What:** Replace hardcoded `stop_loss_pct` with ATR-based dynamic stops.  
`stop = entry_price - 2 * ATR(14)` — adapts to each asset's volatility.  
**Depends on:** FEAT-01.

---

### FEAT-08: Daily Loss Limit Circuit Breaker ✅ DONE
**Status:** `[x]`  
**Impact:** ★★★★★  
**File:** `run_hour.py`  
**What:** Track daily P&L. If it drops below -3% of starting capital, stop all new trades.  
Most important risk management rule. Takes 30 minutes to implement.  
**Depends on:** Nothing.

---

### FEAT-09: Market Hours Awareness ✅ DONE
**Status:** `[x]`  
**Impact:** ★★★☆☆  
**File:** `run_hour.py`  
**What:** Skip stock trades (AAPL, MSFT, GOOGL, TSLA) outside NYSE hours (9:30–16:00 ET).  
Crypto (BTC, ETH) can trade 24/7. Pre/after-market data is noisy.  
**Depends on:** Nothing.

---

### FEAT-10: News Sentiment Score in Prompt ✅ DONE
**Status:** `[x]`  
**Impact:** ★★★☆☆  
**File:** `src/intelligence/strategies/atlas_strategy.py`, `src/data/providers/news_aggregator.py`, `run_hour.py`  
**What:** Convert raw headlines into a numeric sentiment score (-1.0 to +1.0) using provider sentiment parsers,  
then pass that score into the trading decision prompt.  
**Depends on:** FEAT-05.

---

### FEAT-11: Correlation-Based Position Limits ✅ DONE
**Status:** `[x]`  
**Impact:** ★★★☆☆  
**File:** `run_hour.py`, `src/execution/risk/`  
**What:** Block new BUY if two or more correlated assets are already long.  
Groups: [AAPL, MSFT, GOOGL, TSLA] = Tech, [BTC-USD, ETH-USD] = Crypto.  
**Depends on:** Nothing.

---

### FEAT-12: Backtesting Framework ✅ DONE
**Status:** `[x]`  
**Impact:** ★★★★★  
**File:** `backtest.py` (new entry point)  
**What:** Replay historical OHLCV data through the full strategy pipeline.  
Measure Sharpe ratio, max drawdown, win rate, profit factor.  
**Depends on:** FEAT-01 through FEAT-07 (test them all together).

---

## Implementation Order

```
FEAT-01 → FEAT-02 → FEAT-03 → FEAT-04   [FeatureEngineer upgrades, all in parallel]
         ↓
       FEAT-05                            [Better LLM prompt]
         ↓
  FEAT-06 + FEAT-07 + FEAT-08 + FEAT-09  [Risk management, can overlap]
         ↓
       FEAT-10 + FEAT-11                  [Advanced improvements]
         ↓
       FEAT-12                            [Backtest everything]
```

---

## Progress

| Feature | Status | Impact |
|---------|--------|--------|
| FEAT-01: RSI | `[x]` | ★★★★★ |
| FEAT-02: MACD | `[x]` | ★★★★★ |
| FEAT-03: Bollinger Bands | `[x]` | ★★★☆☆ |
| FEAT-04: Volume Ratio | `[x]` | ★★★★☆ |
| FEAT-05: Better LLM Prompt | `[x]` | ★★★★★ |
| FEAT-06: Position Memory | `[x]` | ★★★★☆ |
| FEAT-07: ATR Stop-Loss | `[x]` | ★★★★★ |
| FEAT-08: Daily Loss Limit | `[x]` | ★★★★★ |
| FEAT-09: Market Hours | `[x]` | ★★★☆☆ |
| FEAT-10: News Sentiment Score | `[x]` | ★★★☆☆ |
| FEAT-11: Correlation Limits | `[x]` | ★★★☆☆ |
| FEAT-12: Backtesting | `[x]` | ★★★★★ |
