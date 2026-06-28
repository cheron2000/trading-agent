# 🤖 ATLAS — Adaptive AI Trading Agent

An AI-powered paper trading system built in Python (Google Colab) that uses Claude (claude-sonnet-4-6) as a live tactical decision engine.

## Architecture

```
Live Market Data (yfinance + Yahoo RSS)
         ↓
  Market State Vector
  (price · technicals · sentiment)
         ↓
  Context Memory Injection
  (ATLAS's own prior decisions)
         ↓
  ATLAS LLM Decision Engine
  (BUY / SELL / HOLD + confidence)
         ↓
  Confidence Calibration Layer
  (Quarter-Kelly + drawdown throttle)
         ↓
  Paper Portfolio Execution Engine
  (positions · PnL · win rate · drawdown)
```

## Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ Complete | Environment & real-time data setup |
| 2 | ✅ Complete | Live multi-factor ingestion pipeline |
| 3 | 🔄 In Progress | Prompt engineering for real-time decisions |
| 4 | 🔄 In Progress | Simulated live execution (paper trading) |
| 5 | ⏳ Planned | Safety guardrails & live deployment |

## Colab Cells

| File | Cells | Description |
|------|-------|-------------|
| `notebooks/cell_1_to_7_main.py` | 1–7 | Core system: data pipeline, ATLAS engine, portfolio, trading loop, chart |
| `notebooks/cell_8_confidence_calibration.py` | 8 | Quarter-Kelly sizing + drawdown throttle |
| `notebooks/cell_9_context_memory.py` | 9 | Rolling decision memory buffer + LLM injection |

## Quick Start

1. Open [Google Colab](https://colab.new)
2. Create 9 cells, paste each file's `CELL_N` blocks in order
3. Run Cell 1 → installs dependencies
4. Run Cell 2 → enter your [Anthropic API key](https://console.anthropic.com/)
5. Run Cells 3–9 → loads all modules
6. Run Cell 6 → starts the live paper trading loop

## Tech Stack

- **LLM**: Claude Sonnet 4.6 (Anthropic)
- **Market Data**: yfinance, Yahoo Finance RSS
- **Indicators**: RSI, MACD, Bollinger Bands, ATR, VWAP, SMA, EMA
- **Sizing**: Quarter-Kelly Criterion with drawdown throttle
- **Memory**: Rolling ring buffer with retrospective PnL enrichment

## ⚠️ Disclaimer

This is a paper trading simulation for educational and research purposes only.
No real money is involved. Not financial advice.
