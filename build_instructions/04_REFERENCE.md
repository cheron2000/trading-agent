# Reference: Current File Locations and Key Line Numbers

This file provides exact file paths and line numbers that the building agent
should reference when making modifications.

> **WARNING:** Line numbers may shift if files have been edited since this
> reference was written (2026-08-13). Always verify by searching for the
> exact code patterns mentioned, not just line numbers.

---

## Key Files

### Entry Point
- **`run_hour.py`** (915 lines)
  - `sys.path.insert(0, "src")` → Line 26
  - Module imports start → Lines 27-30
  - Initialization block (EventBus, providers, strategy, etc.) → Lines 183-335
  - `trade_memory` initialization → Around line 330
  - Main trading loop starts → Line 483
  - `ticks = provider.fetch_recent(symbol, n=26)` → Line 614
  - `fv = engineer.compute(ticks)` → Line 615
  - ADX Regime Classification → Lines 617-623
  - `pos_context` dictionary construction → Lines 648-664
  - `strategy.evaluate_with_context(fv, position_context=pos_context)` → Line 666

### ATLAS Strategy
- **`src/intelligence/strategies/atlas_strategy.py`** (351 lines)
  - `_build_atlas_prompt()` method → Line 188
  - Position context fields read → Lines 212-220
  - CURRENT STATE prompt section → Lines 233-248
  - DECISION PROCESS section → Lines 249-287
  - `_parse_atlas_response()` method → Line 313
  - Defensive 60% confidence gate → Line 340

### Feature Engineering
- **`src/data/features/feature_engineer.py`** (280 lines)
  - `compute()` public method → Line 82
  - `_compute_features()` → Line 128
  - `_compute_atr()` → Line 236
  - `_compute_rsi()` → Line 249
  - `_ema()` → Line 263

### Data Models
- **`src/data/models/feature_vector.py`** — Frozen dataclass with `symbol`, `timestamp`, `features: dict[str, float]`, `source_quality`
- **`src/data/models/market_tick.py`** — Frozen dataclass with `symbol`, `price`, `volume`, `timestamp`, `source`
- **`src/intelligence/models/decision.py`** — Frozen dataclass with `symbol`, `action`, `confidence`, `rationale`, `strategy_id`

### Data Provider
- **`src/data/providers/yfinance_provider.py`** (443 lines)
  - `fetch(symbol) -> MarketTick` → Line 116
  - `fetch_recent(symbol, n=5) -> list[MarketTick]` → Returns last N ticks

### Requirements
- **`requirements.txt`** — Already contains `scikit-learn>=1.3.0`

### Test Configuration
- **`pytest.ini`** — Configured with `testpaths = src/tests`
- **Existing tests:** 57 tests all passing in `src/tests/`

---

## Package Structure (src/)

```
src/
├── foundation/          # BaseEvent, Config, Enums
├── communication/       # EventBus, RateLimiter
│   └── events/          # Event type definitions
├── data/
│   ├── features/
│   │   └── feature_engineer.py     # ← You will add support_resistance.py here
│   ├── models/
│   │   ├── feature_vector.py
│   │   └── market_tick.py
│   └── providers/
│       └── yfinance_provider.py
├── intelligence/
│   ├── models/
│   │   └── decision.py
│   ├── strategies/
│   │   ├── atlas_strategy.py       # ← You will modify this
│   │   ├── llm_strategy.py
│   │   └── simple_rule_strategy.py
│   └── ml/                         # ← You will CREATE this package
│       ├── __init__.py
│       └── directional_predictor.py
├── execution/
├── analytics/
├── dashboard/
└── tests/                          # ← You will add 2 new test files here
    ├── test_full_pipeline.py
    ├── test_atlas_strategy.py
    ├── test_telegram_notifier.py
    ├── test_alpaca_order_manager.py
    └── test_portfolio_state_event.py
```
