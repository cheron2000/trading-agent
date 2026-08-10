# AI Trading OS — v1.2.0

An event-driven, seven-layer AI trading platform built with Python 3.11+. Features **ATLAS** (Adaptive Tactical LLM Algorithmic System), Candle Intelligence Layer (CIL), live market data feeds (YFinance with Tor IP rotation), live broker integration (Alpaca), Telegram notifications, and a real-time web command dashboard — all wired through a strict event-bus architecture with zero cross-layer imports.

**Latest:** Dual LLM backend (Groq `llama-3.3-70b-versatile` + local Ollama `llama3.1:8b`), Candle Intelligence Layer, Server-Sent Events (SSE) Web Dashboard, multi-timeframe trend filtering, news sentiment context, dynamic ATR trailing stops, and 562 automated tests passing.

---

## 🏛️ Architecture

The system is strictly divided into 7 layers. Each layer communicates **only** through the `EventBus` — never via direct imports across sibling layers.

```
L1  Foundation (Atlas)          — BaseEvent, Logger, ConfigManager, Bounded Regex Validation
L2  Communication (Hermes)      — EventBus, Scheduler, HealthMonitor, RateLimiter
L3  Data (Orion)                — YFinanceProvider (Tor Proxy), FeatureEngineer (RSI, MACD, BB, ATR, VWAP), NewsAggregator
L4  Intelligence (Athena)       — AtlasStrategy, CandleStrategy (CIL), OllamaStrategy, SimpleRuleStrategy
L5  Execution (Apollo-Exec)     — RiskEngine, OrderManager, AlpacaOrderManager, PortfolioTracker
L6  Analytics (Apollo-Analytics)— MetricsEngine, TradeJournal (SHA-256 Hash Chain), ReportGenerator
L7  Dashboard (Helios)          — Web Dashboard (Flask + SSE), TelegramNotifier
```

### Event Flow Pipeline

```
YFinance / Tor Proxy → DataPipeline → FeatureVectorEvent (RSI, MACD, BB, ATR, VWAP)
                     → ADX Market Regime Classifier (Trending / Ranging / Volatile / Crisis)
                     → Multi-Timeframe Daily Trend Filter & News Sentiment Integration
                     → ATLAS Strategy (6-Step Regime-Gated Confluence + CIL Model Override)
                     → DecisionEvent
                     → RiskEngine (Daily Loss -3%, Volatility Sizing, Correlation Limits)
                     → OrderManager / AlpacaOrderManager → FillEvent
                     → PortfolioTracker + MetricsEngine + TradeJournal
                     → Live Web Dashboard (SSE Stream) + Telegram Alerts
```

---

## 📁 Project Structure

```
ai-trading-os/
├── src/
│   ├── foundation/             # L1 — BaseEvent, Logger, ConfigManager, Security Validation
│   ├── communication/          # L2 — EventBus, Scheduler, HealthMonitor, RateLimiter
│   ├── data/                   # L3 — YFinanceProvider, FeatureEngineer, RegimeClassifier, NewsAggregator
│   ├── intelligence/           # L4 — AtlasStrategy, CandleStrategy, OllamaStrategy, SimpleRuleStrategy
│   ├── execution/              # L5 — RiskEngine, OrderManager, AlpacaOrderManager, PortfolioTracker
│   ├── analytics/              # L6 — MetricsEngine, TradeJournal, ReportGenerator
│   ├── dashboard/              # L7 — Web Dashboard (Flask + SSE), Telegram Notifier
│   └── tests/                  # 562 Unit & Integration Tests (100% Pass Rate)
│
├── data_store/
│   ├── memory/                 # JSONL trade reflections & LLM self-reflection memory
│   └── fixtures/               # Offline market tick datasets (AAPL, MSFT, GOOGL, BTC, ETH, TSLA)
│
├── .github/workflows/          # CI/CD — Ruff, Black, MyPy, Pytest, Architecture Lint
├── run_hour.py                 # Main live trading loop & execution engine
├── mypy.ini                    # MyPy type checking configuration
├── ruff.toml                   # Ruff linter rules & exclusions
└── requirements.txt            # Production dependencies
```

---

## 🌟 Key Features

### 🧠 Intelligence & AI Strategies
- **ATLAS Strategy** — 6-Step regime-gated tactical system powered by dual LLMs (Groq `llama-3.3-70b-versatile` with automatic key rotation, falling back to local Ollama `llama3.1:8b`).
  1. *Circuit Breaker Check* — Evaluates system safety flags.
  2. *Regime Gating* — ADX & ATR ratio classification (Trending, Ranging, Volatile, Crisis).
  3. *3-Layer Confluence Scoring* — Trend (MACD), Momentum (RSI), Volatility (Bollinger Bands).
  4. *Context Memory Anti-Drift* — Injects holdings, P&L, hold cycles, and past reflections.
  5. *Dynamic ATR Risk & 2:1 R:R Gate* — Enforces minimum 2:1 Reward-to-Risk ratio.
  6. *Quarter-Kelly Confidence Calibration* — Outputs 0-100 score mapped to position sizing.
- **Candle Intelligence Layer (CIL)** — Standalone pattern classifier (`CandleStrategy`) overriding `HOLD` decisions when strong candlestick patterns emerge.
- **Multi-Timeframe Trend Filter** — Daily 50-SMA trend filter prevents buying against macro downtrends.
- **Trade Memory & Self-Reflection** — JSONL-backed historical trade lessons injected into LLM prompts.

### 🛡️ Risk Management & Execution
- **Dynamic Trailing Stop-Loss** — Ratchets upwards only (`max(prev_stop, price - 2*ATR)`) to lock in profits.
- **Volatility-Adjusted Position Sizing** — Scales position size inversely to market ATR volatility.
- **Correlation Limits** — Restricts maximum concurrent positions in correlated assets (e.g., BTC/ETH).
- **Daily Loss Circuit Breaker** — Auto-halts trading if daily drawdown exceeds -3%.
- **Live Broker Adapter** — Native integration with Alpaca Markets API (paper & live trading support).

### 🌐 Data & Network Resilience
- **Tor Proxy Rotation** — Automatic IP rotation via Tor SOCKS5 proxy when YFinance hits HTTP 429 rate limits.
- **Real Historical Data Processing** — Preserves real candlestick series for accurate technical indicators.
- **News Sentiment Integration** — Asynchronous news fetch thread (5s cap) enriching prompts without blocking execution loops.

### 💻 Live Command Dashboard
- **Real-Time Web Dashboard** — Flask app served at `http://127.0.0.1:5000` with Server-Sent Events (SSE).
- **Mid-Session Strategy Switcher** — Hot-swap active strategies (`ATLAS`, `GROQ-LLM`, `OLLAMA`, `SIMPLE-RULE`) on the fly.
- **Emergency Kill Switch** — One-click immediate loop termination.
- **Interactive Controls** — Manual tick trigger, trade log filters, equity curve visualizations.

---

## 🛠️ Getting Started

### Prerequisites
- Python 3.11+
- Git

### Installation

```bash
# Clone repository
git clone https://github.com/cheron2000/trading-agent
cd trading-agent

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Running the Live Trading Engine

```bash
# Run trading loop (default 60 minutes, web dashboard at http://127.0.0.1:5000)
python run_hour.py --minutes 60 --strategy ATLAS

# Run with local Ollama fallback
python run_hour.py --minutes 120 --strategy OLLAMA
```

### Running the Web Dashboard Standalone

```bash
python -m dashboard.web.app
```

---

## 🧪 Testing & Code Quality

The repository maintains rigorous quality standards verified on every commit:

```bash
# Run full 562-test suite
pytest src/ --tb=short

# Run AST Architecture Lint (enforces zero illegal cross-layer imports)
python scripts/architecture_lint.py

# Code Formatting & Linting
ruff check src/
black --check src/
```

### Test Suite Summary

| Layer / Component | Test Suite Location | Test Count | Status |
|:---|:---|:---:|:---:|
| L1 Foundation | `src/foundation/tests/` | ~40 | ✅ PASS |
| L2 Communication | `src/communication/tests/` | ~100 | ✅ PASS |
| L3 Data | `src/data/tests/` | ~87 | ✅ PASS |
| L4 Intelligence | `src/intelligence/tests/` | ~180 | ✅ PASS |
| L5 Execution | `src/execution/tests/` | ~45 | ✅ PASS |
| L6 Analytics | `src/analytics/tests/` | ~30 | ✅ PASS |
| L7 Dashboard & Web | `src/dashboard/web/tests/` | ~25 | ✅ PASS |
| **Total Automated Tests** | | **562** | **100% PASS** |

---

## 🔒 Security & Architecture Rules

1. **No Cross-Layer Imports Rule:**
   - Downward dependency flow only: `Dashboard → Analytics → Execution → Intelligence → Data → Communication → Foundation`.
   - Direct imports across sibling layers are strictly forbidden and blocked by AST linting.
2. **Path Traversal Security (CWE-22):** All file reads and writes use `.resolve()` and path validation.
3. **ReDoS Protection (CWE-1333):** All regular expressions use bounded quantifiers.
4. **Immutable State Models:** Event models use `@dataclass(frozen=True, slots=True)` to guarantee thread safety across subscribers.

---

## 🗺️ Real-Money Roadmap

- [x] L1-L7 Core Architecture & EventBus
- [x] ATLAS Dual-LLM Strategy Engine (Groq + Ollama)
- [x] Candle Intelligence Layer (CIL) & Technical Indicators (RSI, MACD, BB, ATR, VWAP)
- [x] Dynamic Trailing Stops & Volatility-Based Position Sizing
- [x] Flask + SSE Command Dashboard & Telegram Alerts
- [ ] Historical Backtesting Engine with Slippage & Commission Simulation
- [ ] Quarter-Kelly Position Sizing & Persistent Cross-Session Equity Tracker
- [ ] 30-Day Automated Alpaca Paper Validation Sprint
- [ ] Live Deployment (Crypto First: BTC-USD, ETH-USD)

---

## 📜 License

MIT License
