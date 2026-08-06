# AI Trading OS — Complete System Architecture

**Version:** v1.0.1+web-dashboard  
**Date:** July 27, 2026  
**Status:** Operational (Paper Trading + Web Dashboard)

---

## System Overview

A **7-layer event-driven algorithmic trading platform** that fetches real market data, applies AI-driven trading strategies, executes orders in paper-trading mode, and streams live metrics to a browser dashboard.

**Key Property:** All cross-layer communication happens exclusively via **EventBus** — zero direct imports between layers.

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────────────────┐
│ L7: Dashboard (Helios)                                                   │
│     ├─ Web UI (Flask + Chart.js): http://127.0.0.1:5000                │
│     ├─ LiveView (Terminal): Real-time trade log                        │
│     └─ Telegram Notifier: Trade alerts (future)                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↑
                              EventBus.publish()
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ L6: Analytics (Apollo-Analytics)                                        │
│     ├─ MetricsEngine: Sharpe, max drawdown, win rate, P&L              │
│     ├─ TradeJournal: SHA-256 hash-chained audit trail                  │
│     └─ ReportGenerator: Final performance report                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↑
                              FillEvent
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ L5: Execution (Apollo-Exec)                                             │
│     ├─ RiskEngine: Confidence threshold, position sizing, symbol check │
│     ├─ OrderManager: Paper execution (live mode raises NotImplemented)│
│     ├─ AlpacaOrderManager: Live Alpaca broker integration (future)     │
│     └─ PortfolioTracker: Position tracking, VWAP averaging            │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↑
                            Order → FillEvent
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ L4: Intelligence (Athena)                                               │
│     ├─ SimpleRuleStrategy: Threshold-based (price_change_pct > ±t%)    │
│     ├─ LLMAgent: Groq LLM-powered decisions (with prompt builder)      │
│     ├─ DecisionMemory: Rolling decision history (deque)                │
│     └─ PromptBuilder: Deterministic, injection-resistant prompts      │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↑
                        FeatureVectorEvent
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ L3: Data (Orion)                                                        │
│     ├─ MarketDataProvider: Fixture-backed (data_store/fixtures/)      │
│     ├─ YFinanceProvider: Live via yfinance (with Tor proxy support)    │
│     ├─ FeatureEngineer: 8 deterministic features per symbol           │
│     │  └─ price_latest, price_mean, price_std, price_change_pct, ... │
│     ├─ MarketNormalizer: Strict validation (never silent drops)       │
│     └─ DataPipeline: fetch → normalize → engineer → publish           │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↑
                         MarketTick (per symbol)
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ L2: Communication (Hermes)                                              │
│     ├─ EventBus: Thread-safe, fnmatch wildcard subscriptions          │
│     ├─ Scheduler: Daemon thread execution with cancellation           │
│     ├─ RateLimiter: Per-namespace rate limiting (data, intelligence..│
│     ├─ HealthMonitor: Liveness detection & auto-register             │
│     └─ Models: EventEnvelope, Subscription, Heartbeat, etc.          │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↑
                         Event subscription / publication
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ L1: Foundation (Atlas)                                                  │
│     ├─ BaseEvent: event_type, event_id, occurred_at, correlation_id   │
│     ├─ ConfigManager: YAML-backed singleton config                    │
│     ├─ Logger: Structured logging with safe path resolution           │
│     ├─ IDGenerator: UUID4-based unique event IDs                      │
│     ├─ Serialization: JSON + schema versioning                        │
│     ├─ Validation: Bounded regex (CWE-1333 safe), path traversal fix  │
│     └─ Utils: Time, versioning, constants, enums                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Event Flow Diagram

```
┌─ START (run_hour.py) ─┐
│ Capital: $100k        │
│ Symbols: AAPL,MSFT... │
└───────────┬───────────┘
            │
            ↓
        EventBus initialized
        └─ Rate limiter configured
        └─ All layers wired
            │
            ↓
    ┌───────────────────────────┐
    │ MAIN TRADING LOOP         │
    │ (60s cycle per iteration) │
    └───────┬───────────────────┘
            │
            ↓
    ┌─────────────────────────────────────┐
    │ For each SYMBOL (AAPL, MSFT, ...):  │
    └────────────┬────────────────────────┘
                 │
                 ├─ [L3] Fetch latest price
                 │   └─ MarketDataProvider.fetch(symbol)
                 │       └─ Returns: MarketTick(price, volume, ts)
                 │
                 ├─ [L3] Fetch recent 5-tick history
                 │   └─ DataPipeline.fetch_recent(symbol, n=5)
                 │       └─ Returns: [MarketTick, MarketTick, ...]
                 │
                 ├─ [L3] Engineer features from ticks
                 │   └─ FeatureEngineer.compute(ticks)
                 │       └─ Outputs: FeatureVector with 8 features
                 │           ├─ price_latest, price_mean, price_std
                 │           ├─ price_change_pct ← KEY for SimpleRuleStrategy
                 │           ├─ volume_mean, volume_total, high, low
                 │           └─ Timestamp: UTC
                 │
                 ├─ [EventBus] Publish FeatureVectorEvent
                 │   └─ Pattern: "data.feature_vector"
                 │       └─ Subscribed by: Dashboard, (future: reporters)
                 │
                 ├─ [L4] Strategy evaluation
                 │   └─ SimpleRuleStrategy.evaluate(feature_vector)
                 │       ├─ IF price_change_pct > +0.3%  → BUY
                 │       ├─ ELIF price_change_pct < -0.3% → SELL
                 │       └─ ELSE                           → HOLD
                 │       └─ Returns: Decision(action, confidence, rationale)
                 │
                 ├─ [EventBus] Publish DecisionEvent
                 │   └─ Pattern: "intelligence.decision"
                 │       └─ Subscribed by: RiskEngine, Dashboard
                 │
                 ├─ [L5] Risk gate
                 │   └─ RiskEngine.approve(decision, portfolio)
                 │       ├─ HOLD → None (skip execution)
                 │       ├─ confidence < 0.3 → None (skip execution)
                 │       ├─ unknown symbol → None (skip execution)
                 │       └─ Otherwise → Order(symbol, action, qty, ...)
                 │
                 ├─ [L5] Order execution
                 │   └─ OrderManager.execute(order)
                 │       ├─ Check drawdown limits
                 │       ├─ Check capital limits (2% per order)
                 │       ├─ Simulate fill at current price
                 │       └─ Returns: FillEvent(symbol, action, qty, fill_price)
                 │
                 ├─ [L5] Apply fill to portfolio
                 │   └─ PortfolioTracker.apply_fill(fill)
                 │       └─ Updates: positions, cash, VWAP averages
                 │
                 ├─ [EventBus] Publish FillEvent
                 │   └─ Pattern: "execution.fill"
                 │       └─ Subscribed by: Analytics, Dashboard, Journal
                 │
                 └─ [L6] Record in audit trail
                     └─ TradeJournal.record(fill, decision_event)
                         └─ Hash-chained tamper detection

            ↓ (repeat for next symbol or end of cycle)
    
    ┌────────────────────────────────────┐
    │ END OF CYCLE:                      │
    ├────────────────────────────────────┤
    │ • Compute metrics (Sharpe, etc)   │
    │ • Push state to dashboard         │
    │ • Sleep 60s (or trigger manual)   │
    └────────────────────────────────────┘
            │
            ↓
    Wait for manual tick or timeout → loop continues
    (Kill switch: stop immediately)
            │
            ↓
    ┌─────────────────────────┐
    │ SESSION END             │
    ├─────────────────────────┤
    │ • Publish "session.end" │
    │ • Generate final report │
    │ • Print P&L summary     │
    └─────────────────────────┘
```

---

## Decision Confidence Problem

**Current Issue:** Confidence always shows **100%** (1.0)

**Root Cause:**  
The `SimpleRuleStrategy` uses this formula:
```python
confidence = min(abs(price_change_pct) / threshold, 1.0)
```

With threshold=0.3% and fixture data showing price changes of 5–10%+:
- `confidence = min(10 / 0.3, 1.0) = min(33.3, 1.0) = 1.0` (capped at 100%)

**Solution Options:**

| Option | Tradeoff |
|--------|----------|
| **Increase threshold to 5%** | Fewer trades, more realistic confidence range |
| **Change formula to sigmoid** | Smoother confidence curve (0.5 at threshold) |
| **Use better fixture data** | More realistic price movements (±0.5% typical) |
| **Add confidence penalty** | Confidence = (pct % threshold) × 0.5 (max 50%) |

---

## Key Components

### L1: Foundation (Atlas)
- **BaseEvent**: Frozen dataclass with immutable event identity
- **Logger**: Structured logging to file with path traversal fix (CWE-22)
- **ConfigManager**: Singleton YAML config loader
- **Validation**: Bounded regex patterns (CWE-1333 safe)

### L2: Communication (Hermes)
- **EventBus**: Thread-safe with RLock, fnmatch wildcards
  - Pattern examples: `"data.feature_vector"`, `"execution.fill"`, `"intelligence.decision"`
- **Scheduler**: Daemon threads with threading.Event cancellation
- **RateLimiter**: Per-namespace token buckets (data, intelligence, execution)

### L3: Data (Orion)
- **MarketDataProvider**: Fixture-backed (instant, no network)
  - Loads from `data_store/fixtures/market_ticks.json`
  - Cycles through ticks for multi-day simulation
- **YFinanceProvider**: Live data via yfinance (with Tor support)
- **FeatureEngineer**: 5-tick window → 8 normalized features
- **DataPipeline**: Fetch → Normalize → Engineer → Publish

### L4: Intelligence (Athena)
- **SimpleRuleStrategy**: `price_change_pct > ±threshold → BUY/SELL/HOLD`
- **LLMAgent**: Groq LLM-powered decisions (future: production)
- **DecisionMemory**: Deque-based decision history for backtesting
- **PromptBuilder**: Sorted features, numeric-only (injection-resistant)

### L5: Execution (Apollo-Exec)
- **RiskEngine**: Filters by confidence (min 0.3), position sizing, symbol validation
- **OrderManager**: Paper execution (live mode raises NotImplementedError)
- **AlpacaOrderManager**: Alpaca broker integration (future, gated by validation)
- **PortfolioTracker**: Wraps Portfolio, returns immutable Position snapshots
- **Portfolio**: Thread-safe (Lock), VWAP averaging, cash tracking

### L6: Analytics (Apollo-Analytics)
- **MetricsEngine**: SELL-only P&L realization
  - Sharpe = (mean / std) × √252 (annualized)
  - Max drawdown (peak-to-trough)
  - Win rate (% profitable trades)
- **TradeJournal**: SHA-256 hash-chained append-only log
  - Detects tampering via `verify_integrity()`
- **ReportGenerator**: Combines metrics + journal into final report dict

### L7: Dashboard (Helios)
- **Flask Web App** (`http://127.0.0.1:5000`)
  - `/`: Full command dashboard (HTML + Chart.js)
  - `/api/snapshot`: JSON state
  - `/stream`: SSE real-time updates
  - `/api/control/tick`, `/control/strategy`, `/control/kill`
- **DashboardState**: Module-level singleton state
  - `push_trade()`, `push_decision()`, `push_warning()`, `push_news()`
  - SSE broadcasting to connected browser clients
- **Telegram Notifier**: Trade alerts via Telegram bot (future)

---

## Thread Safety & Concurrency

| Component | Thread Safety | Mechanism |
|-----------|---------------|-----------|
| EventBus | ✅ Yes | RLock, handler calls outside lock |
| Portfolio | ✅ Yes | threading.Lock |
| DashboardState | ✅ Yes | threading.Lock for reads/writes |
| FeatureEngineer | ⚠️ Stateless | No lock needed (functional) |
| MetricsEngine | ⚠️ Append-only | No lock (consumer-side sync) |
| TradeJournal | ✅ Yes | Lock on append + hash verification |

---

## Security Hardening (v1.0.1)

| Vulnerability | Fix |
|---------------|-----|
| **CWE-22**: Path Traversal | `.resolve()` in logger, config_manager, serialization, validation, market_provider |
| **CWE-396**: Swallowed Exception | `_log.exception(...)` in scheduler.py |
| **CWE-1333**: ReDoS | Bounded regex quantifiers (`{1,100}` not `+`) in validation.py |

---

## Event Patterns & Subscriptions

```
data.feature_vector
  └─ Subscribers: Dashboard, (future: reporters, alerts)
  └─ Payload: FeatureVector(symbol, features, timestamp, source_quality)

intelligence.decision
  └─ Subscribers: RiskEngine, Dashboard, Telegram notifier
  └─ Payload: DecisionEvent(symbol, action, confidence, rationale, strategy_id)

execution.fill
  └─ Subscribers: PortfolioTracker, MetricsEngine, TradeJournal, Dashboard
  └─ Payload: FillEvent(symbol, action, quantity, fill_price, timestamp)

health.heartbeat.recorded
  └─ Subscribers: Dashboard, HealthMonitor
  └─ Payload: Heartbeat(component, status, timestamp)

portfolio.state
  └─ Subscribers: Dashboard, Telegram notifier
  └─ Payload: PortfolioStateEvent(portfolio_value, cash, positions, pnl, return_pct)

system.shutdown_requested
  └─ Subscribers: Main loop
  └─ Payload: BaseEvent (triggers graceful shutdown)
```

---

## Execution Flow (Detailed)

### Single Cycle (60 seconds)

```
START CYCLE
│
├─ For symbol in [AAPL, MSFT, GOOGL, BTC-USD, ETH-USD, TSLA]:
│  │
│  ├─ [L3] fetch(symbol) → MarketTick(price=$150.25, volume=1.2M, ts=2026-07-27T14:03:49Z)
│  │       └─ Source: MarketDataProvider (fixture) or YFinanceProvider (live)
│  │
│  ├─ [L3] fetch_recent(symbol, n=5) → [MarketTick, ..., MarketTick]
│  │       └─ 5-tick window for feature computation
│  │
│  ├─ [L3] engineer.compute(ticks) → FeatureVector
│  │       ├─ price_change_pct = (150.25 - 149.50) / 149.50 = +0.50%
│  │       ├─ price_mean = 150.02 (across 5 ticks)
│  │       ├─ volume_mean = 1.15M
│  │       └─ ... (8 total features)
│  │
│  ├─ [EventBus] publish(FeatureVectorEvent(...))
│  │       └─ Async notification to all "data.feature_vector" subscribers
│  │
│  ├─ [L4] strategy.evaluate(feature_vector) → Decision
│  │       ├─ IF price_change_pct (0.50%) > threshold (0.30%)
│  │       │  └─ action = "BUY"
│  │       │  └─ confidence = min(0.50 / 0.30, 1.0) = min(1.67, 1.0) = 1.0 ← ISSUE HERE
│  │       │  └─ rationale = "price_change_pct=0.50% exceeds threshold +0.30%..."
│  │       │
│  │       └─ Returns Decision(AAPL, BUY, 1.0, rationale, "simple-rule-t0.3")
│  │
│  ├─ [EventBus] publish(DecisionEvent(...))
│  │       └─ Async notification to RiskEngine, Dashboard, Telegram
│  │
│  ├─ [L5] risk_engine.approve(decision, portfolio) → Order or None
│  │       ├─ IF action == "HOLD" → return None (skip)
│  │       ├─ ELIF confidence < 0.3 → return None (skip)
│  │       ├─ ELIF symbol unknown → return None (skip)
│  │       └─ ELSE
│  │           └─ qty = (portfolio.cash * 0.10) / price
│  │           └─ return Order(AAPL, BUY, qty, MARKET, ...)
│  │
│  ├─ [L5] order_manager.execute(order) → FillEvent
│  │       ├─ Check drawdown: if (peak - current) / peak > 10% → reject
│  │       ├─ Check capital: if qty × price > 0.02 × portfolio_value → reject
│  │       ├─ Simulate fill at current_price (paper mode)
│  │       └─ Return FillEvent(AAPL, BUY, qty=66.67, fill_price=$150.25, ts=...)
│  │
│  ├─ [L5] tracker.apply_fill(fill)
│  │       └─ Portfolio.apply_buy(AAPL, 66.67, 150.25)
│  │           ├─ cash -= 66.67 × 150.25 = $10,018.68
│  │           ├─ positions[AAPL] = (66.67, 150.25)
│  │           └─ portfolio_value = cash + Σ(qty × price)
│  │
│  ├─ [EventBus] publish(FillEvent(...))
│  │       └─ Async notification to MetricsEngine, TradeJournal, Dashboard
│  │
│  ├─ [L6] metrics.record_fill(fill, entry_price=150.25)
│  │       └─ On SELL: pnl = (fill_price - entry_price) × quantity
│  │       └─ Append to _equity_curve for drawdown calculation
│  │
│  └─ [L6] journal.record(fill, decision_event)
│         └─ SHA-256 hash chain: new_hash = SHA256(prev_hash + fill_json)
│         └─ Append to JSONL file (immutable audit trail)
│
├─ [L6] metrics.compute() → PerformanceMetrics
│       ├─ total_trades = len([fills])
│       ├─ total_pnl = Σ(pnl per SELL)
│       ├─ sharpe_ratio = (mean(pnls) / std(pnls)) × √252
│       ├─ max_drawdown = (peak - trough) / peak
│       └─ win_rate = count(pnl > 0) / total_trades
│
├─ [L7] dashboard_state.update_portfolio(...)
│       └─ Push metrics, positions, trades to browser via SSE
│
├─ Sleep 60s (or until manual tick or kill switch)
│
└─ END CYCLE
```

---

## Web Dashboard (L7)

**URL:** `http://127.0.0.1:5000`

**Real-time Displays:**
- Portfolio Value (equity curve via Chart.js)
- Max Drawdown, Win Rate, Sharpe Ratio
- Open Positions (with entry prices)
- Recent Trades (with P&L)
- Latest Decisions (symbol, action, confidence, rationale)
- System Status (online/offline pulse)

**Control APIs:**
- `POST /api/control/tick` → Force manual trading cycle
- `POST /api/control/strategy` → Switch strategy mid-session
- `POST /api/control/kill` → Emergency stop

**Data Flow:**
1. run_hour.py updates `dashboard_state` singleton every cycle
2. Dashboard_state broadcasts via SSE (`/stream`) to connected browsers
3. Browser dashboard receives snapshots, updates charts in real-time
4. User clicks "Kill Switch" → `/api/control/kill` → dashboard_state.request_kill()
5. Main loop polls kill flag, stops gracefully

---

## Data Flow Diagram (Simplified)

```
┌──────────────────────┐
│ Market Data Sources  │
│ (Fixture or Live)    │
└──────────┬───────────┘
           │
           ↓
┌──────────────────────────────┐
│ L3: Feature Engineer         │
│ (5-tick window → 8 features) │
└──────────┬───────────────────┘
           │ FeatureVectorEvent
           ↓
┌──────────────────────────────┐
│ L4: Strategy (Rule or LLM)   │
│ (Decision: BUY/SELL/HOLD)    │
└──────────┬───────────────────┘
           │ DecisionEvent
           ↓
┌──────────────────────────────┐
│ L5: Risk Gate                │
│ (confidence, position size)  │
└──────────┬───────────────────┘
           │ Order (if approved)
           ↓
┌──────────────────────────────┐
│ L5: Paper Execution          │
│ (simulated fill at price)    │
└──────────┬───────────────────┘
           │ FillEvent
           ↓
┌──────────────────────────────┐
│ L6: Analytics                │
│ (Metrics, Journal, Report)   │
└──────────┬───────────────────┘
           │
           ↓
┌──────────────────────────────┐
│ L7: Dashboard                │
│ (Web UI, Telegram alerts)    │
└──────────────────────────────┘
```

---

## Running the System

```bash
# Start 30-minute paper trading session
python run_hour.py --minutes 30 --capital 100000

# Watch the dashboard
# Open: http://127.0.0.1:5000

# Available controls:
# - Kill Switch: Stop immediately
# - Manual Tick: Force next cycle now
# - Strategy Swap: Switch SIMPLE-RULE ↔ GROQ-LLM (when configured)
```

**Output:**
- Terminal: Cycle-by-cycle trade log + final P&L report
- Dashboard: Live metrics, equity curve, positions, decision history
- Journal: `data_store/live/journal-live-run-2026-07-27-HHMM.jsonl` (SHA-256 hash-chained)

---

## Future Enhancements

| Phase | Feature |
|-------|---------|
| **Phase 2** | Historical backtesting harness (multi-year OHLCV replay) |
| **Phase 3** | Walk-forward validation (train/test rolling windows) |
| **Phase 4** | Risk hardening (max daily loss, correlation-aware sizing) |
| **Phase 5** | Extended paper trading deployment (cloud VPS, email alerts) |
| **Phase 6** | Live broker integration (Alpaca, Interactive Brokers) |
| **Phase 7** | Compliance & tax reporting (trade export, audit logs) |

---

## Files & Directories

```
ai-trading-os/
├── run_hour.py                 # Entry point (30-min paper trading)
├── run_simulation.py           # Full 7-layer integration test
├── ARCHITECTURE.md             # This file
├── README.md                   # Feature summary
├── requirements.txt            # Dependencies (Flask, hypothesis, etc.)
│
├── src/
│  ├── foundation/             # L1: BaseEvent, Logger, Config, Utils
│  ├── communication/          # L2: EventBus, Scheduler, RateLimiter
│  ├── data/                   # L3: Providers, Features, Pipeline
│  ├── intelligence/           # L4: Strategies, LLM Agent, Memory
│  ├── execution/              # L5: Risk, Orders, Portfolio Tracking
│  ├── analytics/              # L6: Metrics, Journal, Reports
│  ├── dashboard/              # L7: Web UI, Telegram (future), Terminal
│  └── tests/                  # Integration tests (55 total)
│
├── data_store/
│  ├── fixtures/               # market_ticks.json (test data)
│  └── live/                   # journal-*.jsonl (audit trail, runtime)
│
└── scripts/
   └── architecture_lint.py    # Enforces layer boundaries (no illegal imports)
```

---

## Confidence Fix Recommendation

**Immediate:** Change threshold from 0.3% to 5%
```python
strategy = SimpleRuleStrategy(threshold=5.0)  # was: 0.3
```

**Mid-term:** Implement confidence scaling formula:
```python
confidence = min(abs(pct) / threshold, 1.0) * 0.5  # caps at 50%
```

This produces:
- HOLD → 0% confidence (uncertain)
- 1× threshold → 25% confidence (weak signal)
- 2× threshold → 50% confidence (strong signal)
- 3×+ threshold → 50% confidence (maxed out)

This is more realistic for production trading.
