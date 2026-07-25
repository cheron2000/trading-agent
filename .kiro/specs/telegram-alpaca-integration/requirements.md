# Requirements Document

## Introduction

This feature adds two extensions to the AI Trading OS:

1. **TelegramNotifier** — a L7 Dashboard extension that runs alongside the existing `LiveView` terminal dashboard. It publishes trade alerts, daily P&L summaries, news+AI decision digests, and responds to operator commands (`/status`, `/positions`, `/stop`, `/pnl`) via the Telegram Bot API. All inbound queries are answered from EventBus-sourced state; no direct cross-layer imports are permitted.

2. **AlpacaOrderManager** — a L5 Execution extension that implements the same interface as the existing `OrderManager`. It connects to Alpaca's paper trading REST API by default and can switch to live trading only when `live_trading=True` is set explicitly and a confirmation acknowledgement is provided. Risk limits (max 2% capital per trade, stop-all at >10% drawdown) are enforced before any Alpaca order is submitted. Credentials are loaded from `keys.env`. All cross-layer communication remains EventBus-only.

---

## Glossary

- **TelegramNotifier**: The new L7 Dashboard component that sends messages and handles commands via the Telegram Bot API using `python-telegram-bot`.
- **AlpacaOrderManager**: The new L5 Execution component that routes orders through the Alpaca broker REST API.
- **Alpaca_Paper_API**: Alpaca's free paper trading REST endpoint (`https://paper-api.alpaca.markets`).
- **Alpaca_Live_API**: Alpaca's live trading REST endpoint (`https://api.alpaca.markets`).
- **EventBus**: The L2 Hermes publish/subscribe message bus — the only permitted cross-layer communication channel.
- **FillEvent**: The immutable frozen dataclass published to the EventBus after any order execution (existing).
- **DecisionEvent**: The immutable frozen dataclass carrying a BUY/SELL/HOLD signal from L4 Intelligence (existing).
- **FeatureVectorEvent**: The immutable frozen dataclass carrying computed market features from L3 Data (existing).
- **OrderManager**: The existing L5 paper trading order executor (`execution.engine.order_manager`).
- **RiskEngine**: The existing L5 risk gate and position sizer (`execution.risk.risk_engine`).
- **PortfolioTracker**: The existing L5 portfolio state tracker (`execution.engine.portfolio_tracker`).
- **LiveView**: The existing L7 terminal dashboard (`dashboard.shell.live_view`).
- **Drawdown**: The percentage decline in portfolio value from its peak value observed during the current session.
- **Trade_Alert**: A Telegram message sent when a BUY or SELL order is filled.
- **Daily_PnL_Summary**: A Telegram message sent at the end of a trading session containing aggregated P&L metrics.
- **News_Decision_Digest**: A Telegram message sent each cycle containing the news headlines and AI decision for a symbol.
- **live_trading**: A boolean flag that, when set to `True`, enables routing orders to `Alpaca_Live_API` instead of `Alpaca_Paper_API`.
- **paper_validation_complete**: A boolean constructor parameter that must be set to `True` alongside `live_trading=True` to activate the live trading path, confirming that the 30-day paper trading validation has been reviewed.
- **keys.env**: The environment variable file at the project root containing API credentials (existing).

---

## Requirements

### Requirement 1: Telegram Trade Alerts

**User Story:** As a trader, I want to receive a Telegram message whenever a BUY or SELL order is filled, so that I can monitor executed trades without watching the terminal.

#### Acceptance Criteria

1. WHEN a `FillEvent` with `action="BUY"` is received on the EventBus, THE `TelegramNotifier` SHALL send a Telegram message containing the symbol, quantity (rounded to 4 decimal places), fill price (formatted to 2 decimal places), and the UTC timestamp of the fill.
2. WHEN a `FillEvent` with `action="SELL"` is received on the EventBus, THE `TelegramNotifier` SHALL send a Telegram message containing the symbol, quantity (rounded to 4 decimal places), fill price (formatted to 2 decimal places), realized P&L (formatted to 2 decimal places with sign), and the UTC timestamp of the fill.
3. IF the Telegram Bot API call fails, THEN THE `TelegramNotifier` SHALL log the failure at WARNING level using the configured logger; IF logging itself fails, THE `TelegramNotifier` SHALL halt further operation and raise the logging exception.
4. THE `TelegramNotifier` SHALL receive all trading data exclusively via EventBus subscriptions, with zero direct imports from L3, L4, or L5 modules.

---

### Requirement 2: Daily P&L Summary

**User Story:** As a trader, I want to receive a daily summary of P&L metrics at the end of each session, so that I can review trading performance without opening the terminal.

#### Acceptance Criteria

1. WHEN a session ends (triggered by a `session.end` event on the EventBus), THE `TelegramNotifier` SHALL send a Telegram message containing: total P&L (formatted to 2 decimal places with sign), win rate (as a percentage to 1 decimal place), total round-trip trades, Sharpe ratio (to 4 decimal places), and max drawdown (as a percentage to 4 decimal places).
2. WHEN a session ends and zero trades were executed during the session, THE `TelegramNotifier` SHALL send a Telegram message stating that no trades were executed and the portfolio value (formatted to 2 decimal places).
3. IF the Telegram Bot API call fails during summary delivery, THEN THE `TelegramNotifier` SHALL log the failure at WARNING level; IF logging itself fails, THE `TelegramNotifier` SHALL halt further operation and raise the logging exception.

---

### Requirement 3: News and AI Decision Digest

**User Story:** As a trader, I want to receive the news context and AI decision for each symbol each cycle, so that I can understand what information is driving each trade signal.

#### Acceptance Criteria

1. WHEN a `DecisionEvent` is received on the EventBus, THE `TelegramNotifier` SHALL send a Telegram message containing the symbol, action (BUY/SELL/HOLD), confidence score (to 2 decimal places), and the first 200 characters of the rationale.
2. WHERE the `TelegramNotifier` is configured with `notify_hold=False`, THE `TelegramNotifier` SHALL suppress Telegram messages for `DecisionEvent` instances with `action="HOLD"`.
3. WHERE the `TelegramNotifier` is configured with `notify_hold=True`, THE `TelegramNotifier` SHALL send Telegram messages for all `DecisionEvent` instances including `action="HOLD"`.
4. IF the Telegram Bot API call fails during digest delivery, THEN THE `TelegramNotifier` SHALL log the failure at WARNING level; IF logging itself fails, THE `TelegramNotifier` SHALL halt further operation and raise the logging exception.

---

### Requirement 4: Telegram Bot Commands

**User Story:** As a trader, I want to send commands to the bot from my phone to query portfolio state and trigger a graceful shutdown, so that I can manage the system remotely.

#### Acceptance Criteria

1. WHEN the `/status` command is received, THE `TelegramNotifier` SHALL reply with the current portfolio value (formatted to 2 decimal places) and cash balance (formatted to 2 decimal places) sourced from the most recent EventBus-published state.
2. WHEN the `/positions` command is received, THE `TelegramNotifier` SHALL reply with a list of all open positions including symbol, quantity (to 4 decimal places), and entry price (to 2 decimal places); IF no open positions exist, THE `TelegramNotifier` SHALL reply with a message stating "No open positions."
3. WHEN the `/pnl` command is received, THE `TelegramNotifier` SHALL reply with total realized P&L (formatted to 2 decimal places with sign) and total return as a percentage (to 4 decimal places) sourced from the most recent EventBus-published state.
4. WHEN the `/stop` command is received, THE `TelegramNotifier` SHALL publish a `system.shutdown_requested` event on the EventBus and, only after the event is successfully published, reply with a confirmation message stating "Shutdown requested. System will stop gracefully."
5. THE `TelegramNotifier` SHALL respond to all four commands (`/status`, `/positions`, `/pnl`, `/stop`) within 5 seconds of receipt under normal operating conditions.
6. IF an unrecognised command is received, THEN THE `TelegramNotifier` SHALL reply with a help message listing the four supported commands and their descriptions.
7. THE `TelegramNotifier` SHALL require zero user authentication, operating as a single-user personal bot.

---

### Requirement 5: TelegramNotifier Initialisation and Configuration

**User Story:** As a developer, I want the TelegramNotifier to load credentials from `keys.env` and integrate cleanly with the existing EventBus, so that it can be added to the system without modifying any frozen layers.

#### Acceptance Criteria

1. THE `TelegramNotifier` SHALL accept an `IEventBus` instance, a `bot_token` string, and a `chat_id` string as constructor parameters.
2. THE `TelegramNotifier` SHALL subscribe to the EventBus patterns `"execution.fill"`, `"intelligence.decision"`, `"session.end"`, and `"portfolio.state"` on `start()`.
3. THE `TelegramNotifier` SHALL unsubscribe from all EventBus patterns on `stop()`.
4. IF `bot_token` is empty or whitespace, THEN THE `TelegramNotifier` SHALL raise a `ValueError` at construction time with the message "bot_token must not be empty."
5. IF `chat_id` is empty or whitespace, THEN THE `TelegramNotifier` SHALL raise a `ValueError` at construction time with the message "chat_id must not be empty."
6. THE `TelegramNotifier` SHALL use the `python-telegram-bot` library (version ≥ 20.0) for all Telegram API calls.

---

### Requirement 6: AlpacaOrderManager Interface Compatibility

**User Story:** As a developer, I want `AlpacaOrderManager` to implement the same interface as the existing `OrderManager`, so that it can be substituted without changing any caller code.

#### Acceptance Criteria

1. THE `AlpacaOrderManager` SHALL expose an `execute(order: Order) -> FillEvent` method with the identical signature as `OrderManager.execute`.
2. WHEN `AlpacaOrderManager.execute` is called with a valid `Order`, THE `AlpacaOrderManager` SHALL submit a market order to the Alpaca API, await fill confirmation, construct a `FillEvent` with `event_type="execution.fill"`, and publish it on the EventBus.
3. WHEN the Alpaca API returns a fill, THE `AlpacaOrderManager` SHALL populate the `FillEvent.fill_price` with the average fill price returned by the Alpaca API.
4. IF the Alpaca API returns an error response, THEN THE `AlpacaOrderManager` SHALL raise a `RuntimeError` with the Alpaca error message included in the exception message, and shall not publish a `FillEvent`.
5. THE `AlpacaOrderManager` SHALL require zero direct imports from L3, L4, or L6 modules, communicating exclusively via EventBus and constructor-injected dependencies.

---

### Requirement 7: Alpaca Paper Trading Mode

**User Story:** As a developer, I want `AlpacaOrderManager` to default to Alpaca's paper trading API, so that the system can be validated safely before any real capital is committed.

#### Acceptance Criteria

1. THE `AlpacaOrderManager` SHALL default to `live_trading=False`, routing all orders to `Alpaca_Paper_API` (`https://paper-api.alpaca.markets`).
2. WHEN `AlpacaOrderManager` is constructed with `live_trading=False`, THE `AlpacaOrderManager` SHALL connect to `Alpaca_Paper_API` and log the active endpoint at INFO level.
3. WHEN `AlpacaOrderManager.execute` is called in paper mode, THE `AlpacaOrderManager` SHALL submit the order to `Alpaca_Paper_API` and return a `FillEvent` populated with the simulated fill data returned by the paper API.
4. THE `AlpacaOrderManager` SHALL load `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` from `keys.env` using the existing `load_keys` module.
5. IF `ALPACA_API_KEY` or `ALPACA_SECRET_KEY` are absent from `keys.env`, THEN THE `AlpacaOrderManager` SHALL raise a `ValueError` at construction time with the message "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in keys.env."
6. IF `keys.env` does not exist or cannot be parsed, THEN THE `AlpacaOrderManager` SHALL raise a `FileNotFoundError` or `IOError` (as appropriate) at construction time with a message describing the file access failure, distinct from the missing-key `ValueError`.

---

### Requirement 8: Live Trading Gate

**User Story:** As a developer, I want live trading to be explicitly gated behind a flag and paper validation acknowledgement, so that accidental real-money execution is impossible.

#### Acceptance Criteria

1. WHEN `AlpacaOrderManager` is constructed with `live_trading=True` and `paper_validation_complete=True`, THE `AlpacaOrderManager` SHALL route all orders to `Alpaca_Live_API` (`https://api.alpaca.markets`) and log a WARNING-level message stating the live trading mode is active.
2. WHEN `AlpacaOrderManager` is constructed with `live_trading=True` and `paper_validation_complete=False`, THE `AlpacaOrderManager` SHALL raise a `ValueError` with the message "Live trading requires paper_validation_complete=True to confirm 30-day validation has been reviewed."
3. WHEN `AlpacaOrderManager` is constructed with `live_trading=True` and `paper_validation_complete` is not provided, THE `AlpacaOrderManager` SHALL raise a `ValueError` with the message "Live trading requires paper_validation_complete=True to confirm 30-day validation has been reviewed."
4. THE `AlpacaOrderManager` SHALL treat `live_trading=True` as a permanent session flag — THE `AlpacaOrderManager` SHALL NOT provide a method to switch between paper and live modes after construction.

---

### Requirement 9: Risk Limits for Alpaca Orders

**User Story:** As a trader, I want the AlpacaOrderManager to enforce hard risk limits before submitting any order to Alpaca, so that a bug or strategy error cannot cause catastrophic losses.

#### Acceptance Criteria

1. WHILE an order is pending execution, THE `AlpacaOrderManager` SHALL reject any order where the notional value (quantity × current price) exceeds 2% of the total portfolio value at the time of the call, and shall not submit that order to the Alpaca API.
2. WHILE the session Drawdown exceeds 10% of the peak portfolio value observed during the session, THE `AlpacaOrderManager` SHALL reject all incoming orders and publish a `risk.drawdown_breach` event on the EventBus containing the current drawdown percentage.
3. IF an order is rejected due to the 2% capital limit, THEN THE `AlpacaOrderManager` SHALL log the rejection at WARNING level, stating the symbol, notional value, and the 2% limit that was breached.
4. IF an order is rejected due to drawdown breach, THEN THE `AlpacaOrderManager` SHALL log the rejection at WARNING level, stating the current drawdown percentage and the 10% threshold.
5. THE `AlpacaOrderManager` SHALL track the session peak portfolio value internally, updating it whenever a new portfolio value exceeds the recorded peak.
6. WHEN `AlpacaOrderManager` is constructed, THE `AlpacaOrderManager` SHALL accept an `initial_portfolio_value` float parameter used to set the initial peak value for drawdown tracking.

---

### Requirement 10: Alpaca Position and Portfolio Queries

**User Story:** As a developer, I want to query open positions and portfolio value from Alpaca directly, so that the EventBus state can be kept in sync with the actual broker state.

#### Acceptance Criteria

1. THE `AlpacaOrderManager` SHALL expose a `get_positions() -> list[dict]` method that calls the Alpaca positions endpoint and returns a list of position dictionaries each containing `symbol`, `quantity`, and `market_value`.
2. THE `AlpacaOrderManager` SHALL expose a `get_portfolio_value() -> float` method that calls the Alpaca account endpoint and returns the total equity value as a float.
3. WHEN `get_positions()` is called and the Alpaca API returns open positions, THE `AlpacaOrderManager` SHALL return the actual position data; WHEN the Alpaca API returns no open positions, THE `AlpacaOrderManager` SHALL return an empty list.
4. IF the Alpaca API returns an error on `get_positions()` or `get_portfolio_value()`, THEN THE `AlpacaOrderManager` SHALL raise a `RuntimeError` with the Alpaca error message.

---

### Requirement 11: Architecture Compliance

**User Story:** As a developer, I want both new components to comply with the existing architecture rules, so that the `scripts/architecture_lint.py` CI check continues to pass.

#### Acceptance Criteria

1. THE `TelegramNotifier` SHALL be placed in the `src/dashboard/` package (L7), with no direct imports from `src/execution/`, `src/intelligence/`, `src/data/`, or `src/analytics/`.
2. THE `AlpacaOrderManager` SHALL be placed in the `src/execution/` package (L5), with no direct imports from `src/dashboard/`, `src/intelligence/`, `src/data/`, or `src/analytics/`.
3. WHEN `scripts/architecture_lint.py` is executed after adding both components, THE Architecture_Linter SHALL report zero cross-layer import violations; THE `TelegramNotifier` and `AlpacaOrderManager` SHALL contain zero cross-layer imports at all times, regardless of whether the linter is executed.
4. THE `AlpacaOrderManager` SHALL use the `alpaca-trade-api` or `alpaca-py` library (pinned exact version in `requirements.txt`) for all Alpaca REST API calls.
5. THE `TelegramNotifier` SHALL use the `python-telegram-bot` library (pinned exact version in `requirements.txt`) for all Telegram Bot API calls.

---

### Requirement 12: Paper Trading Validation Before Live Activation

**User Story:** As a developer, I want the system to enforce that paper trading validation completes before live trading is activated, so that no real capital is risked on an unvalidated strategy.

#### Acceptance Criteria

1. THE `AlpacaOrderManager` documentation (docstring) SHALL state that `live_trading=True` must not be used until a 30-day paper trading validation run has been completed and reviewed.
2. WHEN `AlpacaOrderManager` is constructed with `live_trading=True`, THE `AlpacaOrderManager` SHALL print a WARNING-level log message stating: "LIVE TRADING ACTIVE — ensure 30-day paper validation has been completed and reviewed before using this mode."
3. WHEN `AlpacaOrderManager` is constructed with `live_trading=True` and `paper_validation_complete=True`, THE `AlpacaOrderManager` SHALL proceed to activate the live trading path without requiring a separate `Confirmation_Acknowledgement` string.
4. WHEN `AlpacaOrderManager` is constructed with `live_trading=True` and `paper_validation_complete` is not provided or is `False`, THE `AlpacaOrderManager` SHALL raise a `ValueError` with the message "Live trading requires paper_validation_complete=True to confirm 30-day validation has been reviewed." before making any network connection to `Alpaca_Live_API`.
