# Implementation Plan: telegram-alpaca-integration

## Overview

Implement two new components — `TelegramNotifier` (L7 Dashboard) and `AlpacaOrderManager` (L5 Execution) — plus the shared `PortfolioStateEvent` and credential-loading helpers. All communication is EventBus-only. The work is divided into: foundation (shared event + credentials), the Alpaca order manager, the Telegram notifier, `run_hour.py` wiring, and CI/architecture compliance.

---

## Tasks

- [x] 1. Extend credentials infrastructure and add PortfolioStateEvent

  - [x] 1.1 Add `load_telegram_keys` and `load_alpaca_keys` to `load_keys.py`
    - Implement `load_telegram_keys(path) -> tuple[str, str]` that reads `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from `keys.env`; raise `FileNotFoundError` if the file is missing, `ValueError` if either key is absent or empty
    - Implement `load_alpaca_keys(path) -> tuple[str, str]` that reads `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` from `keys.env` with the same error semantics
    - _Requirements: 7.4, 7.5, 7.6, 5.1_

  - [x] 1.2 Add Telegram and Alpaca credential stubs to `keys.env`
    - Append the `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ALPACA_API_KEY`, and `ALPACA_SECRET_KEY` keys (with empty values and explanatory comments) to `keys.env`
    - _Requirements: 7.4, 5.1_

  - [x] 1.3 Create `src/communication/events/portfolio_state_event.py`
    - Define the frozen dataclass `PortfolioStateEvent(BaseEvent)` with fields: `event_type="portfolio.state"`, `portfolio_value`, `cash`, `realized_pnl`, `total_return_pct`, `positions: tuple[dict, ...]`
    - Add `__init__.py` updates so the event is importable from `communication.events`
    - _Requirements: 5.2, 4.1, 4.2, 4.3_

  - [ ]* 1.4 Write unit tests for `load_telegram_keys` and `load_alpaca_keys`
    - Test missing-file path raises `FileNotFoundError`
    - Test missing key raises `ValueError`
    - Test empty key raises `ValueError`
    - Test happy path returns correct tuple
    - _Requirements: 7.5, 7.6_

- [x] 2. Implement AlpacaOrderManager

  - [x] 2.1 Create package skeleton `src/execution/broker/`
    - Create `src/execution/broker/__init__.py`
    - Create stub `src/execution/broker/alpaca_order_manager.py` with class signature, docstring, and all method stubs raising `NotImplementedError`
    - Pin `alpaca-py` exact version in `requirements.txt`
    - _Requirements: 6.1, 11.2, 11.4_

  - [x] 2.2 Implement `AlpacaOrderManager.__init__` with live-trading gate and credential validation
    - Load `api_key` / `secret_key` via constructor params (caller uses `load_alpaca_keys`)
    - Raise `ValueError` if `live_trading=True` and `paper_validation_complete` is not `True`, with the exact required message
    - Instantiate `TradingClient` with `paper=True` or `paper=False` based on `live_trading`
    - Log INFO for paper mode (URL), WARNING for live mode ("LIVE TRADING ACTIVE — ensure 30-day paper validation...")
    - Set `self._peak_portfolio_value = initial_portfolio_value`
    - _Requirements: 7.1, 7.2, 8.1, 8.2, 8.3, 8.4, 12.1, 12.2, 12.3, 12.4_

  - [ ]* 2.3 Write unit tests for `AlpacaOrderManager.__init__` validation
    - `live_trading=True, paper_validation_complete=False` → `ValueError` with exact message
    - `live_trading=True, paper_validation_complete` omitted → `ValueError`
    - Paper mode → `TradingClient` called with `paper=True`, INFO log
    - Live mode → `TradingClient` called with `paper=False`, WARNING log
    - _Requirements: 8.2, 8.3, 12.2_

  - [x] 2.4 Implement `_check_capital_limit`, `_check_drawdown_limit`, and `_update_peak`
    - `_check_capital_limit(order, current_price)`: reject if `quantity × current_price > 0.02 × portfolio_value`; log WARNING with symbol, notional, and limit; raise `ValueError`
    - `_check_drawdown_limit()`: reject if `(peak - current) / peak > 0.10`; log WARNING; publish `risk.drawdown_breach` event; raise `ValueError`
    - `_update_peak(current_value)`: update `self._peak_portfolio_value` if `current_value` exceeds it
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ]* 2.5 Write property test for capital limit (Property 10)
    - **Property 10: Orders exceeding 2% of portfolio value are rejected**
    - **Validates: Requirements 9.1**
    - Use `hypothesis` strategies generating random `quantity`, `price`, and `portfolio_value`; assert rejection when `quantity × price > 0.02 × portfolio_value` and pass-through otherwise
    - _Test file: `src/execution/broker/tests/test_alpaca_order_manager_props.py`_

  - [ ]* 2.6 Write property test for drawdown rejection and peak tracking (Property 11)
    - **Property 11: All orders are rejected when session drawdown exceeds 10%, and drawdown breach event is published**
    - **Validates: Requirements 9.2, 9.5**
    - Use `hypothesis` `st.lists(st.floats(min_value=1.0), min_size=2)` to generate portfolio value sequences; feed them as `get_portfolio_value()` mock returns; assert peak equals running maximum and orders rejected when drawdown > 10%
    - _Test file: `src/execution/broker/tests/test_alpaca_order_manager_props.py`_

  - [x] 2.7 Implement `AlpacaOrderManager.execute`
    - Call `_check_drawdown_limit()` then `_check_capital_limit(order, current_price)`
    - Submit market order via `alpaca_client.submit_order()`; await fill via `alpaca_client.get_order_by_id()` polling or websocket; raise `RuntimeError("Alpaca fill timeout for order {order_id}")` on timeout
    - On API error, raise `RuntimeError(f"Alpaca API error: {message}")` without publishing a `FillEvent`
    - Construct `FillEvent` with `fill_price = avg_fill_price` from API response, publish on EventBus, return the event
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 2.8 Write property test for `execute()` FillEvent correctness (Property 9)
    - **Property 9: AlpacaOrderManager execute() produces a correctly populated FillEvent from API response**
    - **Validates: Requirements 6.2, 6.3**
    - Mock `TradingClient` to return random `avg_fill_price`; use `st.builds(Order)` for orders; assert all FillEvent fields match order and API response, and event published exactly once
    - _Test file: `src/execution/broker/tests/test_alpaca_order_manager_props.py`_

  - [ ]* 2.9 Write unit tests for `execute()` error paths
    - Alpaca API error → `RuntimeError`, no `FillEvent` published
    - Fill timeout → `RuntimeError`
    - _Requirements: 6.4_

  - [x] 2.10 Implement `get_positions` and `get_portfolio_value`
    - `get_positions()`: call `alpaca_client.get_all_positions()`; map each position to `{"symbol": ..., "quantity": ..., "market_value": ...}`; return empty list when API returns no positions; raise `RuntimeError` on API error
    - `get_portfolio_value()`: call `alpaca_client.get_account()`; return `float(account.equity)`; raise `RuntimeError` on API error
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ]* 2.11 Write property test for `get_positions()` mapping (Property 12)
    - **Property 12: get_positions() maps Alpaca API response to standard dict structure**
    - **Validates: Requirements 10.1, 10.3**
    - Use `st.lists(st.fixed_dictionaries(...))` of mock Alpaca position objects; assert every returned dict contains exactly `"symbol"`, `"quantity"`, `"market_value"` keys
    - _Test file: `src/execution/broker/tests/test_alpaca_order_manager_props.py`_

- [x] 3. Checkpoint — AlpacaOrderManager complete
  - Ensure all AlpacaOrderManager tests pass. Run `python -m pytest src/execution/broker/tests/ -v`. Ask the user if any questions arise before proceeding.

- [x] 4. Implement TelegramNotifier

  - [x] 4.1 Create package skeleton `src/dashboard/telegram/`
    - Create `src/dashboard/telegram/__init__.py`
    - Create stub `src/dashboard/telegram/telegram_notifier.py` with class signature and all method stubs
    - Pin `python-telegram-bot>=20.0` exact version in `requirements.txt`
    - _Requirements: 5.6, 11.1, 11.5_

  - [x] 4.2 Implement `TelegramNotifier.__init__`, `start`, and `stop`
    - Validate `bot_token` and `chat_id` at construction; raise `ValueError("bot_token must not be empty.")` / `ValueError("chat_id must not be empty.")` on empty/whitespace
    - `start()`: subscribe to `"execution.fill"`, `"intelligence.decision"`, `"session.end"`, `"portfolio.state"`; build `Application`; spin up daemon thread with dedicated asyncio loop running `application.run_polling()`
    - `stop()`: stop polling, stop the event loop, join the thread, unsubscribe all four patterns
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 4.3 Write property test for start/stop subscription round-trip (Property 13)
    - **Property 13: TelegramNotifier start()/stop() subscription round-trip**
    - **Validates: Requirements 5.2, 5.3**
    - Run `start()` then `stop()` ≥100 times using `@settings(max_examples=100)`; assert EventBus subscription count returns to its pre-`start()` value after each `stop()`
    - _Test file: `src/dashboard/telegram/tests/test_telegram_notifier_props.py`_

  - [ ]* 4.4 Write unit tests for `__init__`, `start`, and `stop` validation
    - Empty `bot_token` → `ValueError` with exact message
    - Empty `chat_id` → `ValueError` with exact message
    - `start()` registers exactly four EventBus subscriptions
    - `stop()` unregisters all subscriptions
    - _Requirements: 5.4, 5.5_

  - [x] 4.5 Implement message formatter methods
    - `_format_fill_message(event, realized_pnl)`: BUY path includes symbol, qty (4dp), price (2dp), UTC timestamp; SELL path additionally includes realized P&L (2dp with sign)
    - `_format_decision_message(event)`: symbol, action, confidence (2dp), rationale truncated to first 200 chars
    - `_format_session_summary(event)`: total P&L (2dp with sign), win rate (1dp%), total trades (int), Sharpe (4dp), max drawdown (4dp%); if `total_trades==0`, format "no trades" message with portfolio value (2dp)
    - `_format_status_reply()`, `_format_positions_reply()`, `_format_pnl_reply()`: read from in-memory `_state` cache populated by `_on_portfolio()`
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 3.1, 4.1, 4.2, 4.3_

  - [ ]* 4.6 Write property test for BUY fill message fields (Property 1)
    - **Property 1: BUY fill message contains all required fields**
    - **Validates: Requirements 1.1**
    - `st.builds(FillEvent, action=st.just("BUY"), ...)` with arbitrary symbol, quantity, fill price, timestamp; assert formatted string contains all four required fields with correct precision
    - _Test file: `src/dashboard/telegram/tests/test_telegram_notifier_props.py`_

  - [ ]* 4.7 Write property test for SELL fill message fields (Property 2)
    - **Property 2: SELL fill message contains all required fields including P&L**
    - **Validates: Requirements 1.2**
    - `st.builds(FillEvent, action=st.just("SELL"), ...)` plus `st.floats()` for entry price; assert P&L computed correctly and all five fields present with correct precision
    - _Test file: `src/dashboard/telegram/tests/test_telegram_notifier_props.py`_

  - [ ]* 4.8 Write property test for decision digest truncation (Property 3)
    - **Property 3: Decision digest message contains symbol, action, confidence, and truncated rationale**
    - **Validates: Requirements 3.1**
    - `st.builds(DecisionEvent, rationale=st.text(min_size=0, max_size=500))`; assert rationale in message is ≤200 chars
    - _Test file: `src/dashboard/telegram/tests/test_telegram_notifier_props.py`_

  - [ ]* 4.9 Write property test for HOLD suppression (Property 4)
    - **Property 4: HOLD events are suppressed when notify_hold=False**
    - **Validates: Requirements 3.2**
    - `st.builds(DecisionEvent, action=st.just("HOLD"))`; assert `bot.send_message` never called when `notify_hold=False`
    - _Test file: `src/dashboard/telegram/tests/test_telegram_notifier_props.py`_

  - [ ]* 4.10 Write property test for HOLD sent when notify_hold=True (Property 5)
    - **Property 5: All decision events including HOLD are sent when notify_hold=True**
    - **Validates: Requirements 3.3**
    - Same strategy as above but `notify_hold=True`; assert `bot.send_message` called exactly once per event
    - _Test file: `src/dashboard/telegram/tests/test_telegram_notifier_props.py`_

  - [ ]* 4.11 Write property test for session summary formatting (Property 6)
    - **Property 6: Session summary message contains all five metric fields correctly formatted**
    - **Validates: Requirements 2.1**
    - `st.fixed_dictionaries({"total_pnl": st.floats(...), "win_rate": st.floats(0,1), "total_trades": st.integers(min_value=0), "sharpe_ratio": st.floats(...), "max_drawdown": st.floats(0,1)})`; assert all five fields present with correct precision
    - _Test file: `src/dashboard/telegram/tests/test_telegram_notifier_props.py`_

  - [ ]* 4.12 Write property test for /status reply latest state (Property 7)
    - **Property 7: /status reply contains portfolio value and cash from latest portfolio.state event**
    - **Validates: Requirements 4.1**
    - `st.lists(st.builds(PortfolioStateEvent, ...), min_size=1)`; publish all in sequence; issue `/status`; assert reply reflects last event's values at 2dp
    - _Test file: `src/dashboard/telegram/tests/test_telegram_notifier_props.py`_

  - [ ]* 4.13 Write property test for /positions reply (Property 8)
    - **Property 8: /positions reply lists all positions or reports "No open positions."**
    - **Validates: Requirements 4.2**
    - `st.lists(st.fixed_dictionaries({"symbol": st.text(), "quantity": st.floats(), "entry_price": st.floats()}), max_size=20)`; assert one line per position or exact "No open positions." string
    - _Test file: `src/dashboard/telegram/tests/test_telegram_notifier_props.py`_

  - [x] 4.14 Implement EventBus handlers and `_safe_send`
    - `_on_fill(event)`: format message via `_format_fill_message()`; schedule `_safe_send()` via `asyncio.run_coroutine_threadsafe()`
    - `_on_decision(event)`: respect `notify_hold` flag; format via `_format_decision_message()`; schedule send
    - `_on_session_end(event)`: format via `_format_session_summary()`; schedule send
    - `_on_portfolio(event)`: update `self._portfolio_value`, `self._cash`, `self._positions`, `self._realized_pnl`, `self._total_return_pct` cache from event fields
    - `_safe_send(text)`: `await bot.send_message()`; on `TelegramError` or network error call `self._log.warning(...)`; if logger itself raises, re-raise
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4_

  - [x] 4.15 Implement Telegram command handlers
    - `_cmd_status`: reply with `_format_status_reply()` within 5 seconds
    - `_cmd_positions`: reply with `_format_positions_reply()`; reply "No open positions." when list empty
    - `_cmd_pnl`: reply with `_format_pnl_reply()`
    - `_cmd_stop`: publish `system.shutdown_requested` on EventBus first; only after successful publish reply "Shutdown requested. System will stop gracefully."; log if publish fails
    - `_cmd_unknown`: reply with help message listing all four commands and descriptions
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ]* 4.16 Write unit tests for command handlers and error paths
    - Bot API failure on fill/decision/session → WARNING logged, no crash
    - `/stop` publishes shutdown event before sending reply (ordering assertion)
    - Unknown command → help text contains all four command names
    - _Requirements: 1.3, 2.3, 3.4, 4.4, 4.6_

- [x] 5. Checkpoint — TelegramNotifier complete
  - Ensure all TelegramNotifier tests pass. Run `python -m pytest src/dashboard/telegram/tests/ -v`. Ask the user if any questions arise before proceeding.

- [x] 6. Wire components into run_hour.py

  - [x] 6.1 Add `--telegram` flag: conditional import and `TelegramNotifier` construction
    - After existing imports, add optional block guarded by `"--telegram" in sys.argv`; call `load_telegram_keys()`; construct `TelegramNotifier`; handle `FileNotFoundError`/`ValueError` with a WARNING print (not a crash)
    - _Requirements: 5.1, 5.2, 11.1_

  - [x] 6.2 Add `--alpaca` flag: conditional import and `AlpacaOrderManager` construction
    - Add optional block guarded by `"--alpaca" in sys.argv`; call `load_alpaca_keys()`; construct `AlpacaOrderManager` with `live_trading=False`; fall back to existing `OrderManager` when flag absent
    - _Requirements: 6.1, 7.1, 7.2, 11.2_

  - [x] 6.3 Start `TelegramNotifier` before the trading loop and stop it after
    - Call `_telegram_notifier.start()` after all components are wired; call `_telegram_notifier.stop()` after the session-end event is published
    - _Requirements: 5.2, 5.3_

  - [x] 6.4 Publish `PortfolioStateEvent` at the end of each cycle
    - After all symbols are processed each cycle, compute `portfolio_value`, `cash`, `positions`, `realized_pnl`, and `total_return_pct`; publish `PortfolioStateEvent` on the EventBus
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 6.5 Publish `session.end` event and subscribe `system.shutdown_requested`
    - After the trading loop ends, publish `BaseEvent(event_type="session.end", payload={...})` with all six required fields
    - Add `_on_shutdown_requested` handler subscribed to `"system.shutdown_requested"` that sets the `shutdown` flag
    - _Requirements: 2.1, 4.4_

  - [x] 6.6 Unify order execution dispatch via `_exec` variable
    - Replace both `order_manager.execute(order)` call sites with `_exec.execute(order)` where `_exec = alpaca_order_manager if _use_alpaca else order_manager`
    - _Requirements: 6.1_

- [x] 7. Architecture compliance and dependency pinning

  - [x] 7.1 Verify `scripts/architecture_lint.py` passes with both new components
    - Run `python scripts/architecture_lint.py` and confirm zero violations for `TelegramNotifier` and `AlpacaOrderManager`
    - Fix any accidental cross-layer import if the linter reports one
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 7.2 Pin library versions in `requirements.txt`
    - Add `python-telegram-bot==<latest stable ≥20.0>` with exact pin
    - Add `alpaca-py==<latest stable>` with exact pin
    - Confirm `hypothesis` is present in `requirements-dev.txt` (add if missing)
    - _Requirements: 11.4, 11.5_

- [x] 8. Final checkpoint — all tests pass
  - Run the full test suite: `python -m pytest src/ -v`. Ensure all tests pass, architecture lint is clean, and no cross-layer imports exist. Ask the user if any questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The design uses Python throughout — all code examples should be Python
- `AlpacaOrderManager` tests use `unittest.mock.patch` on `alpaca.trading.client.TradingClient` — no real API calls are made
- `TelegramNotifier` tests mock `python-telegram-bot`'s `Application` and `bot.send_message` to avoid real Telegram calls
- The threading model (daemon thread + `asyncio.run_coroutine_threadsafe`) is the critical integration point — test it carefully in Task 4.3 and 4.14
- Property tests use `hypothesis` with `@settings(max_examples=100)` minimum
- Architecture lint CI is already configured in `.github/workflows/python-ci.yml` — no new CI setup needed

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["1.4", "2.1", "4.1"] },
    { "id": 2, "tasks": ["2.2", "2.4", "2.10", "4.2"] },
    { "id": 3, "tasks": ["2.3", "2.5", "2.6", "2.11", "4.3", "4.4", "4.5"] },
    { "id": 4, "tasks": ["2.7", "4.14", "4.15"] },
    { "id": 5, "tasks": ["2.8", "2.9", "4.6", "4.7", "4.8", "4.9", "4.10", "4.11", "4.12", "4.13"] },
    { "id": 6, "tasks": ["4.16", "6.1", "6.2"] },
    { "id": 7, "tasks": ["6.3", "6.4", "6.5", "6.6"] },
    { "id": 8, "tasks": ["7.1", "7.2"] }
  ]
}
```
