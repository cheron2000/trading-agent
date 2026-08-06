# AI Trading OS — v1.1.0

An event-driven, seven-layer AI trading platform built with Python 3.11+. Features ATLAS strategy (Adaptive Tactical LLM Algorithmic System), live broker integration (Alpaca), Telegram notifications, and a web dashboard — all wired through a strict event-bus architecture with zero cross-layer imports.

**Latest:** Round-robin symbol processing (2 per cycle) for faster Ollama execution, 24/7 crypto markets, Telegram remote monitoring.

---

## Architecture

The system is divided into 7 layers. Each layer communicates **only** through the EventBus — never via direct imports across sibling layers.

```
L1  Foundation (Atlas)          — BaseEvent, Logger, Config, Utils
L2  Communication (Hermes)      — EventBus, Scheduler, HealthMonitor, PortfolioStateEvent
L3  Data (Orion)                — YFinanceProvider, FeatureEngineer, NewsAggregator
L4  Intelligence (Athena)       — AtlasStrategy, SimpleRuleStrategy, LLMStrategy
L5  Execution (Apollo-Exec)     — RiskEngine, AlpacaOrderManager, PortfolioTracker
L6  Analytics (Apollo-Analytics)— MetricsEngine, TradeJournal, ReportGenerator
L7  Dashboard (Helios)          — Web Dashboard, TelegramNotifier
```

### Event Flow

```
DataPipeline → FeatureVectorEvent
             → SimpleRuleStrategy / LLMAgent → DecisionEvent
             → RiskEngine → Order
             → OrderManager → FillEvent
             → PortfolioTracker + MetricsEngine + TradeJournal
             → LiveView (Dashboard)
```

---

## Project Structure

```
src/
├── foundation/             # L1 — BaseEvent, Logger, ConfigManager, utils
├── communication/          # L2 — EventBus, Scheduler, HealthMonitor, models
├── data/                   # L3 — MarketDataProvider, FeatureEngineer, DataPipeline
├── intelligence/           # L4 — SimpleRuleStrategy, LLMAgent, DecisionMemory
├── execution/              # L5 — RiskEngine, OrderManager, PortfolioTracker
├── analytics/              # L6 — MetricsEngine, TradeJournal, ReportGenerator
├── dashboard/              # L7 — LiveView
├── paper_trading/          # PaperTradingRunner — full 7-layer simulation harness
└── tests/                  # Integration tests (55 tests, full pipeline)

data_store/fixtures/        # Fixture market ticks (AAPL, MSFT, GOOGL, BTC-USD, ETH-USD, TSLA)
scripts/architecture_lint.py# AST-based cross-layer import enforcement
.github/workflows/          # CI/CD — ruff, black, mypy, pytest
```

---

## Key Features

### Core Architecture
- **Event-driven architecture** — all cross-layer communication via EventBus with fnmatch wildcard subscriptions
- **Frozen dataclasses** — all models use `@dataclass(frozen=True, slots=True)` for immutability
- **Architecture lint** — `scripts/architecture_lint.py` enforces no illegal cross-layer imports via AST analysis
- **Security hardened** — path traversal (CWE-22) fixed, ReDoS-safe bounded regexes, exception logging

### Trading Strategies
- **ATLAS Strategy** — 6-step regime-gated multi-factor confluence system with dual LLM backend (Groq → Ollama fallback)
- **Rule-based strategy** — `SimpleRuleStrategy` uses technical indicators for deterministic signals
- **LLM strategies** — Groq and Ollama integration with position memory and news context

### Execution & Risk
- **Live broker integration** — Alpaca Markets API (paper/live modes) with `AlpacaOrderManager`
- **Multi-layer risk controls** — 2% capital limit, 10% drawdown stop, correlation limits, ATR-based trailing stops
- **Live trading gate** — requires explicit 30-day paper validation flag
- **Circuit breakers** — daily loss limit (-3%), market hours enforcement

### Monitoring & Analytics
- **Telegram notifications** — real-time trade alerts, remote commands (`/status`, `/positions`, `/pnl`, `/stop`)
- **Web dashboard** — live portfolio view at `http://127.0.0.1:5000` with kill switch
- **Hash-chained journal** — SHA-256 tamper-evident trade logging
- **Performance metrics** — Sharpe ratio (annualised √252), max drawdown, win rate, total P&L

### Optimization
- **Round-robin symbol processing** — 2 symbols per cycle for faster Ollama execution (3 cycles cover all 6 symbols)
- **24/7 crypto markets** — BTC, ETH, SOL, AVAX, MATIC, LINK (no market hours constraints)

---

## Layers in Detail

### L1 — Foundation (Atlas)
- `BaseEvent` — fields: `event_type`, `event_id` (uuid4), `occurred_at` (UTC), `schema_version`, `correlation_id`, `causation_id`
- `ConfigManager` — singleton, YAML-backed
- `Logger` — structured logging with safe path resolution
- `utils/` — `id_generator`, `serialization`, `validation` (bounded regex), `time`

### L2 — Communication (Hermes)
- `EventBus` — thread-safe RLock, fnmatch wildcards, handlers called outside lock
- `Scheduler` — daemon threads, `threading.Event` cancellation, exception logging
- `HealthMonitor` — liveness window, auto-register, optional EventBus integration
- Models: `EventEnvelope`, `EventMetadata`, `Subscription`, `Heartbeat`, `EventPriority`, `HealthState`, `PluginManifest`

### L3 — Data (Orion)
- `MarketDataProvider` — fixture-backed from `data_store/fixtures/market_ticks.json`
- `MarketNormalizer` — strict validation, raises `ValueError` on bad data (never silent drops)
- `FeatureEngineer` — 8 deterministic features: `price_latest`, `price_mean`, `price_std`, `price_change_pct`, `volume_mean`, `volume_total`, `high`, `low`
- `DataPipeline` — fetch → normalize → engineer → publish `FeatureVectorEvent`

### L4 — Intelligence (Athena)
- `SimpleRuleStrategy` — `price_change_pct > threshold` → BUY, `< -threshold` → SELL, else HOLD
- `LLMAgent` — injected `ILLMClient`, strict JSON parse, raises on bad JSON/action/confidence
- `PromptBuilder` — deterministic, sorted features, numeric-only (injection-resistant)
- `DecisionMemory` — `deque(maxlen)`, `add()` / `recent(n)` / `clear()`, `is_empty` property

### L5 — Execution (Apollo-Exec)
- `RiskEngine` — gates: HOLD → None, low confidence → None, unknown symbol → None
- `OrderManager` — paper-only, fills at `price_feed` price, publishes `FillEvent`
- `Portfolio` — thread-safe Lock, VWAP average entry price tracking
- `PortfolioTracker` — wraps Portfolio, `apply_fill`, `get_position`, `portfolio_value`

### L6 — Analytics (Apollo-Analytics)
- `MetricsEngine` — SELL-only P&L, Sharpe = `mean/std * √252`, max drawdown, win rate
- `TradeJournal` — append-only, SHA-256 hash chain, `verify_integrity()`
- `ReportGenerator` — combines MetricsEngine + TradeJournal into a serializable report dict

### L7 — Dashboard (Helios)
- `LiveView` — subscribes to 4 event patterns: `data.feature_vector`, `intelligence.decision`, `execution.fill`, `health.heartbeat.recorded`
- Injectable output stream, `event_count` property

---

## Getting Started

### Requirements
- Python 3.11+
- pip

### Install

```bash
git clone https://github.com/cheron2000/trading-agent
cd trading-agent
pip install -r requirements.txt
```

### Run Paper Trading Simulation

```python
from paper_trading.runner import PaperTradingRunner

runner = PaperTradingRunner(initial_capital=100_000.0, run_days=30)
report = runner.run()

print(report["journal_integrity"])   # True
print(report["metrics"])             # {total_trades, total_pnl, sharpe_ratio, ...}
```

### Run Tests

```bash
pytest src/ --cov=src --cov-report=term-missing --cov-fail-under=80
```

### Run Architecture Lint

```bash
python scripts/architecture_lint.py
```

---

## Tests

| Suite | Location | Count |
|---|---|---|
| Foundation | `src/foundation/` | ~40 |
| Communication | `src/communication/tests/` | ~100 |
| Data | `src/data/tests/` | ~87 |
| Intelligence | `src/intelligence/tests/` | ~55 |
| Execution | `src/execution/tests/` | ~15 |
| Analytics | `src/analytics/tests/` | ~10 |
| Integration (full pipeline) | `src/tests/test_full_pipeline.py` | 55 |
| **Total** | | **~335+** |

---

## Security (v1.0.1 patch)

| Issue | Severity | Fix |
|---|---|---|
| Path traversal CWE-22 | HIGH | `.resolve()` in `logger.py`, `serialization.py`, `config_manager.py`, `validation.py`, `market_provider.py` |
| Swallowed exception CWE-396 | HIGH | `_log.exception(...)` in `scheduler.py` |
| ReDoS CWE-1333 | MEDIUM | Bounded regex quantifiers in `validation.py` |

---

## CI/CD

GitHub Actions runs on every push and pull request:

```
ruff check src/
black --check src/
mypy src/
pytest --cov=src --cov-fail-under=80
python scripts/architecture_lint.py
```

---

## Architecture Rule

> All cross-layer communication happens via EventBus only.
> No direct imports across sibling layers — ever.
> Enforced by `scripts/architecture_lint.py` on every CI run.

---

## Roadmap

- [x] L1 Foundation — frozen v1.0.1
- [x] L2 Communication — frozen v1.0.1
- [x] L3 Data — frozen v1.0.1
- [x] L4 Intelligence — frozen v1.0.0
- [x] L5 Execution — frozen v1.0.0
- [x] L6 Analytics — frozen v1.0.0
- [x] L7 Dashboard — frozen v1.0.0
- [x] Paper trading harness — built
- [ ] 30-day paper trading validation run
- [ ] Live broker adapter (only after paper trading passes + compliance sign-off)
- [ ] Web GUI (Helios phase 2)
- [ ] Experience layer / continual learning

---

## Built With

- **Amazon Q** (Guardian QA) — code review, bug fixes, test writing, security audit
- **Kiro** (Chief Architect) — layer implementation, CI/CD, architecture design

---

## License

MIT
