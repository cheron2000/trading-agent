# AI Trading OS — Developer Guide & Project Overview

Welcome to the **AI Trading OS** developer guide. This document provides a complete technical overview and quick-start roadmap for developers who want to edit, extend, or contribute to this repository.

---

## 1. Project Overview

**AI Trading OS** is an autonomous, event-driven trading system built in Python 3.11+. It features an **Adaptive Tactical LLM Algorithmic System (ATLAS)** powered by sequential multi-key Groq LLM rotation, quantitative risk management gates, a real-time web dashboard, Telegram alerts, and an automated backtesting framework.

### Key Capabilities
- **7-Layer Decoupled Architecture**: Strict separation of concerns from data ingestion to execution and web visualization.
- **ATLAS LLM Strategy**: 6-step decision pipeline utilizing technical confluence (RSI, MACD, Bollinger Bands, ATR, ADX), market regime gating, and news sentiment scoring.
- **Multi-Key LLM Rotation**: Automatic failover across multiple Groq API keys to eliminate rate limits and maintain high throughput ($240+$ req/min capacity).
- **Quantitative Risk Controls**: ATR-based dynamic stop-loss/take-profit targets, 2% capital per-trade cap, 10% session drawdown stop, and correlation-based position limits.
- **Real-Time Web Dashboard**: Flask + HTML5 interface streaming live portfolio state, metrics, decisions, and interactive strategy switching at `http://127.0.0.1:5000`.
- **Backtesting Framework**: Discrete event historical replayer (`backtest.py`) with slippage and commission simulation.

---

## 2. System Architecture (7-Layer Model)

```text
┌────────────────────────────────────────────────────────┐
│  Layer 7: Interface (Web Dashboard / Telegram Bot)      │
└───────────────────────────▲────────────────────────────┘
                            │ (BaseEvent Subscriptions)
┌───────────────────────────┴────────────────────────────┐
│  Layer 6: Analytics (Metrics, Journal, Reports)         │
└───────────────────────────▲────────────────────────────┘
                            │
┌───────────────────────────┴────────────────────────────┐
│  Layer 5: Execution (RiskEngine, OrderManager, Alpaca) │
└───────────────────────────▲────────────────────────────┘
                            │
┌───────────────────────────┴────────────────────────────┐
│  Layer 4: Intelligence (ATLAS, SimpleRule, Ollama)     │
└───────────────────────────▲────────────────────────────┘
                            │
┌───────────────────────────┴────────────────────────────┐
│  Layer 3: Data (YFinance, AlphaVantage, FeatureEng)    │
└───────────────────────────▲────────────────────────────┘
                            │
┌───────────────────────────┴────────────────────────────┐
│  Layer 2: Communication (EventBus, RateLimiter)        │
└───────────────────────────▲────────────────────────────┘
                            │
┌───────────────────────────┴────────────────────────────┐
│  Layer 1: Foundation (BaseEvent, Config, Enums)        │
└────────────────────────────────────────────────────────┘
```

---

## 3. Directory & File Guide

```text
ai-trading-os/
├── run_hour.py              # Main entry point: live paper trading + dashboard
├── backtest.py              # Backtesting entry point: historical replay & metrics
├── load_keys.py             # Key loader & rotation manager (keys.env)
├── test_av_key.py           # Alpha Vantage API key diagnostic script
├── test_groq_key.py         # Groq API key diagnostic script
├── test_key_rotation.py     # Groq key rotation test script
├── pytest.ini               # Pytest configuration (targets src/tests/)
├── keys.env                 # Private API credentials (Git-ignored)
├── FEATURES.md              # Feature roadmap & progress tracker
├── TEST_DEBT.md             # Test coverage tracking & debt log
└── src/
    ├── foundation/          # Layer 1: Core abstractions & base models
    ├── communication/       # Layer 2: EventBus & inter-layer event models
    ├── data/                # Layer 3: Market providers, news, feature engineering
    ├── intelligence/        # Layer 4: ATLAS strategy, prompt builder, LLM engines
    ├── execution/           # Layer 5: Order execution, Alpaca broker, RiskEngine
    ├── analytics/           # Layer 6: Performance metrics, trade journal, report generator
    ├── dashboard/           # Layer 7: Flask web dashboard & Telegram bot
    └── tests/               # Unit & integration test suite (57 passing tests)
```

---

## 4. Where to Start & Quick Launch Commands

### Setup Prerequisites
1. Ensure Python 3.11+ is installed.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `keys.env` file in the root directory with your API keys:
   ```env
   GROQ_API_KEY_1=gsk_xxxxxxxxxxxxxxxx
   GROQ_API_KEY_2=gsk_yyyyyyyyyyyyyyyy
   ALPACA_API_KEY=PKXXXXXXXXXXXXXXXX
   ALPACA_SECRET_KEY=zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz
   ALPHA_VANTAGE_KEY=AVXXXXXXXXXXXXXX
   ```

### Execution Commands

* **Run Live Paper Trading + Dashboard:**
  ```bash
  python run_hour.py --minutes 120 --capital 10000 --strategy ATLAS
  ```
  Open browser at `http://127.0.0.1:5000` to monitor live trading.

* **Run Historical Backtest:**
  ```bash
  python backtest.py --symbol AAPL --days 30 --capital 10000
  ```

* **Run Diagnostic Tests:**
  ```bash
  python test_groq_key.py      # Tests Groq LLM connectivity & rotation
  python test_av_key.py        # Tests Alpha Vantage key quota & health
  ```

* **Run Automated Test Suite:**
  ```bash
  python -m pytest             # Executes all 57 unit tests in src/tests/
  ```

---

## 5. How to Modify or Extend the Project

### A. Adding a New Technical Indicator
1. Open [`src/data/features/feature_engineer.py`](file:///c:/Users/Lenovo/OneDrive/Desktop/shreyash/TradingAgentDirectory-20260715T120313Z-1-001/TradingAgentDirectory/projecttrade/ai-trading-os/src/data/features/feature_engineer.py).
2. Calculate the new indicator inside `compute()` (use standard library math).
3. Add the value to the returned `FeatureVector.features` dictionary.
4. Update [`src/intelligence/strategies/atlas_strategy.py`](file:///c:/Users/Lenovo/OneDrive/Desktop/shreyash/TradingAgentDirectory-20260715T120313Z-1-001/TradingAgentDirectory/projecttrade/ai-trading-os/src/intelligence/strategies/atlas_strategy.py) `_build_atlas_prompt()` to present the new metric to the LLM.

### B. Adding a New Trading Strategy
1. Create a strategy class in `src/intelligence/strategies/` implementing `evaluate(fv)` and `evaluate_with_context(fv, pos_ctx)`.
2. Register the strategy in [`run_hour.py`](file:///c:/Users/Lenovo/OneDrive/Desktop/shreyash/TradingAgentDirectory-20260715T120313Z-1-001/TradingAgentDirectory/projecttrade/ai-trading-os/run_hour.py) under the strategy selection block.

### C. Adding a New Risk Rule
1. Open [`src/execution/risk/risk_engine.py`](file:///c:/Users/Lenovo/OneDrive/Desktop/shreyash/TradingAgentDirectory-20260715T120313Z-1-001/TradingAgentDirectory/projecttrade/ai-trading-os/src/execution/risk/risk_engine.py).
2. Implement your check in `approve(decision_event, portfolio)`. Return `None` to reject risky trades.

---

## 6. Development Roadmap & What to Build Next

- [ ] **30-Day Paper Validation Sprint**: Complete continuous 30-day paper trading run on Alpaca.
- [ ] **Live Execution Gate**: Update [`src/execution/broker/alpaca_order_manager.py`](file:///c:/Users/Lenovo/OneDrive/Desktop/shreyash/TradingAgentDirectory-20260715T120313Z-1-001/TradingAgentDirectory/projecttrade/ai-trading-os/src/execution/broker/alpaca_order_manager.py) (`paper_validation_complete=True`) after paper validation.
- [ ] **Quarter-Kelly Sizing Extension**: Dynamic position sizing scaled directly by ATLAS LLM confidence score.
- [ ] **Multi-Asset Rebalancing**: Automated portfolio exposure balancing across tech equities and major cryptocurrencies.
