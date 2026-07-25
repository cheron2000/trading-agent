# Design Document: telegram-alpaca-integration

## Overview

This feature adds two new components to the AI Trading OS that extend it with live broker execution and remote monitoring via Telegram.

**TelegramNotifier** (`src/dashboard/telegram/telegram_notifier.py`) is a L7 Dashboard component that mirrors the `LiveView` pattern: it subscribes to EventBus events and is read-only with respect to other layers. It adds a bidirectional channel via the Telegram Bot API — sending formatted alerts outbound and handling four operator commands inbound. The bot runs an async polling loop inside a background thread so it does not block the synchronous `run_hour.py` trading loop.

**AlpacaOrderManager** (`src/execution/broker/alpaca_order_manager.py`) is a L5 Execution component that implements the exact same `execute(order) -> FillEvent` interface as the existing `OrderManager`. It replaces the paper fill simulation with real REST calls to Alpaca's paper or live API. Risk limits (2% per-trade cap, 10% drawdown stop) are enforced inside `AlpacaOrderManager` before any order is submitted, providing a second safety layer on top of the existing `RiskEngine`.

Both components communicate exclusively via the EventBus and constructor-injected dependencies, preserving the layered architecture enforced by `scripts/architecture_lint.py`.

---

## Architecture

### Layer Placement

```
L7 Dashboard     ← TelegramNotifier  (new, src/dashboard/telegram/)
L6 Analytics     ← unchanged
L5 Execution     ← AlpacaOrderManager  (new, src/execution/broker/)
                 ← OrderManager (existing, unchanged)
L4 Intelligence  ← unchanged
L3 Data          ← unchanged
L2 Communication ← EventBus (unchanged)
L1 Foundation    ← BaseEvent, FillEvent, DecisionEvent (unchanged)
```

### Data Flow — TelegramNotifier

```
EventBus
  execution.fill      ──► TelegramNotifier._on_fill()      ──► bot.send_message()
  intelligence.decision ► TelegramNotifier._on_decision()  ──► bot.send_message()
  session.end         ──► TelegramNotifier._on_session_end() ► bot.send_message()
  portfolio.state     ──► TelegramNotifier._on_portfolio()  ──► _state (in-memory cache)

Telegram Bot (inbound commands)
  /status   ──► TelegramNotifier._cmd_status()    ──► bot.reply()
  /positions ─► TelegramNotifier._cmd_positions() ──► bot.reply()
  /pnl      ──► TelegramNotifier._cmd_pnl()       ──► bot.reply()
  /stop     ──► TelegramNotifier._cmd_stop()      ──► bus.publish(system.shutdown_requested)
                                                  ──► bot.reply("Shutdown requested...")
```

### Data Flow — AlpacaOrderManager

```
run_hour.py / caller
  execute(order)
    ├─► _check_drawdown_limit() ──► risk.drawdown_breach (EventBus) if breached
    ├─► _check_capital_limit()  ──► WARNING log if breached
    ├─► alpaca_client.submit_order()
    ├─► alpaca_client.await_fill()
    ├─► FillEvent(fill_price=avg_fill_price)
    └─► bus.publish(fill_event)
        └─► returns FillEvent

get_positions()  ──► alpaca_client.list_positions() ──► list[dict]
get_portfolio_value() ─► alpaca_client.get_account() ──► float
```


### Architecture Compliance

The linter in `scripts/architecture_lint.py` enforces a forbidden-import matrix. The two new components must satisfy:

| Component | Layer | Forbidden direct imports |
|---|---|---|
| `TelegramNotifier` | `dashboard` (L7) | `execution`, `intelligence`, `data`, `analytics` |
| `AlpacaOrderManager` | `execution` (L5) | `dashboard`, `analytics`, `intelligence` (L3/L4/L6) |

Both components import only from `foundation`, `communication`, and their own layer, plus the two third-party libraries (`python-telegram-bot`, `alpaca-py`).

---

## Components and Interfaces

### TelegramNotifier

**File:** `src/dashboard/telegram/telegram_notifier.py`

```python
class TelegramNotifier:
    def __init__(
        self,
        bus: IEventBus,
        bot_token: str,
        chat_id: str,
        notify_hold: bool = False,
    ) -> None: ...

    # Lifecycle
    def start(self) -> None: ...
    def stop(self) -> None: ...

    # EventBus handlers (private, called by subscriptions)
    def _on_fill(self, event: BaseEvent) -> None: ...
    def _on_decision(self, event: BaseEvent) -> None: ...
    def _on_session_end(self, event: BaseEvent) -> None: ...
    def _on_portfolio(self, event: BaseEvent) -> None: ...

    # Telegram command handlers (registered with Application)
    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None: ...
    async def _cmd_positions(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None: ...
    async def _cmd_pnl(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None: ...
    async def _cmd_stop(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None: ...
    async def _cmd_unknown(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None: ...

    # Message formatters (private, pure functions — no I/O)
    def _format_fill_message(self, event: BaseEvent, realized_pnl: float | None) -> str: ...
    def _format_decision_message(self, event: BaseEvent) -> str: ...
    def _format_session_summary(self, event: BaseEvent) -> str: ...
    def _format_status_reply(self) -> str: ...
    def _format_positions_reply(self) -> str: ...
    def _format_pnl_reply(self) -> str: ...

    # Safe async send helper
    async def _safe_send(self, text: str) -> None: ...
```

**Internal state (instance attributes):**

```python
self._bus: IEventBus
self._bot_token: str
self._chat_id: str
self._notify_hold: bool
self._subscriptions: list[Subscription]
self._app: Application          # python-telegram-bot Application
self._loop: asyncio.AbstractEventLoop  # dedicated event loop for bot thread
self._thread: threading.Thread

# Portfolio state cache — updated by _on_portfolio()
self._portfolio_value: float = 0.0
self._cash: float = 0.0
self._positions: list[dict] = []
self._realized_pnl: float = 0.0
self._total_return_pct: float = 0.0

# Entry price cache for SELL P&L computation
self._entry_prices: dict[str, float] = {}
```


**Threading model:**

`python-telegram-bot` >= 20 is fully async. `run_hour.py` is synchronous. The solution is to spin up a dedicated asyncio event loop on a background `daemon` thread inside `start()`. The bot's `Application.run_polling()` runs on that loop. EventBus handlers (`_on_fill`, etc.) are called on the main thread; they schedule coroutines onto the bot's loop with `asyncio.run_coroutine_threadsafe(self._safe_send(text), self._loop)`.

```
Main thread (run_hour.py)           Bot thread (daemon)
───────────────────────────         ──────────────────────────────────────
bus.publish(FillEvent)              asyncio event loop running
  → _on_fill() called               Application.run_polling()
    → run_coroutine_threadsafe()  →  _safe_send() awaited
      (Future returned)              bot.send_message() called
```

---

### AlpacaOrderManager

**File:** `src/execution/broker/alpaca_order_manager.py`

```python
class AlpacaOrderManager:
    def __init__(
        self,
        bus: IEventBus,
        initial_portfolio_value: float,
        api_key: str,
        secret_key: str,
        live_trading: bool = False,
        paper_validation_complete: bool = False,
    ) -> None: ...

    # Primary interface — drop-in replacement for OrderManager.execute
    def execute(self, order: Order) -> FillEvent: ...

    # Portfolio/position queries
    def get_positions(self) -> list[dict]: ...
    def get_portfolio_value(self) -> float: ...

    # Risk enforcement (private)
    def _check_capital_limit(self, order: Order, current_price: float) -> None: ...
    def _check_drawdown_limit(self) -> None: ...
    def _update_peak(self, current_value: float) -> None: ...
```

**Internal state:**

```python
self._bus: IEventBus
self._client: TradingClient          # alpaca-py TradingClient
self._live_trading: bool
self._peak_portfolio_value: float    # max observed, for drawdown calc
self._log: logging.Logger
```

**alpaca-py client selection:**

```python
# Paper
from alpaca.trading.client import TradingClient
self._client = TradingClient(api_key, secret_key, paper=True)   # paper=True → paper API

# Live
self._client = TradingClient(api_key, secret_key, paper=False)  # paper=False → live API
```

---

### PortfolioStateEvent (new event for Telegram state sync)

To give `TelegramNotifier` access to portfolio state without importing from L5, `run_hour.py` publishes a lightweight `portfolio.state` event each cycle. This event carries only primitive fields (no L5 objects).

**File:** `src/communication/events/portfolio_state_event.py`

```python
@dataclass(frozen=True, slots=True)
class PortfolioStateEvent(BaseEvent):
    portfolio_value: float = 0.0
    cash: float = 0.0
    realized_pnl: float = 0.0
    total_return_pct: float = 0.0
    positions: tuple[dict, ...] = field(default_factory=tuple)
```

> **Note:** This event lives in `communication/events/` (L2) so it is importable by both L5 (publisher) and L7 (subscriber) without creating a cross-layer import. Each position dict contains `{"symbol": str, "quantity": float, "entry_price": float}`.


---

## Data Models

### FillEvent (existing — unchanged)

```python
@dataclass(frozen=True, slots=True)
class FillEvent(BaseEvent):
    event_type: str           # "execution.fill"
    order_id: str
    symbol: str
    action: Literal["BUY", "SELL"]
    quantity: float
    fill_price: float         # For AlpacaOrderManager: avg_fill_price from Alpaca API
    timestamp: datetime       # UTC
```

### DecisionEvent (existing — unchanged)

```python
@dataclass(frozen=True, slots=True)
class DecisionEvent(BaseEvent):
    event_type: str           # "intelligence.decision"
    symbol: str
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: float         # [0.0, 1.0]
    rationale: str
    strategy_id: str
```

### SessionEndEvent (convention — existing pattern)

`run_hour.py` publishes a generic `BaseEvent` with `event_type="session.end"` and a `payload` dict. The payload must carry:

```python
{
    "total_pnl": float,
    "win_rate": float,       # [0.0, 1.0]
    "total_trades": int,
    "sharpe_ratio": float,
    "max_drawdown": float,   # [0.0, 1.0]
    "portfolio_value": float,
}
```

### PortfolioStateEvent (new)

```python
@dataclass(frozen=True, slots=True)
class PortfolioStateEvent(BaseEvent):
    event_type: str = "portfolio.state"
    portfolio_value: float = 0.0
    cash: float = 0.0
    realized_pnl: float = 0.0
    total_return_pct: float = 0.0
    positions: tuple[dict, ...] = ()
    # Each dict: {"symbol": str, "quantity": float, "entry_price": float}
```

### Credential keys (keys.env additions)

```ini
# Telegram Bot
# ----------------------------------------
# Get token from @BotFather on Telegram.
# chat_id: send a message to your bot then call
#   https://api.telegram.org/bot<TOKEN>/getUpdates
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Alpaca Broker
# ----------------------------------------
# Paper trading: https://app.alpaca.markets (Paper Account)
# Live trading:  https://app.alpaca.markets (Live Account)
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
```

### load_keys.py additions

```python
def load_telegram_keys(path=_DEFAULT_KEYS_FILE) -> tuple[str, str]:
    """Return (bot_token, chat_id) from keys.env.

    Raises:
        FileNotFoundError: If keys.env does not exist.
        ValueError: If either key is missing or empty.
    """

def load_alpaca_keys(path=_DEFAULT_KEYS_FILE) -> tuple[str, str]:
    """Return (api_key, secret_key) from keys.env.

    Raises:
        FileNotFoundError: If keys.env does not exist.
        ValueError: If either key is missing or empty.
    """
```


---

## File Structure

```
src/
├── communication/
│   └── events/
│       └── portfolio_state_event.py   ← NEW (L2 — importable by L5 and L7)
│
├── dashboard/
│   ├── __init__.py
│   └── telegram/
│       ├── __init__.py                ← NEW
│       └── telegram_notifier.py       ← NEW (L7)
│
└── execution/
    ├── __init__.py
    └── broker/
        ├── __init__.py                ← NEW
        └── alpaca_order_manager.py    ← NEW (L5)

(project root)
├── load_keys.py                       ← MODIFIED (add load_telegram_keys, load_alpaca_keys)
└── keys.env                           ← MODIFIED (add Telegram + Alpaca sections)
```

---

## run_hour.py Wiring

The following diff shows exactly how `TelegramNotifier` and `AlpacaOrderManager` plug in without breaking the existing loop. All changes are purely additive — the existing `OrderManager` path is preserved behind the `--alpaca` flag.

### Step 1 — Imports and key loading (top of file, after existing imports)

```python
# Optional Telegram notifier
_telegram_notifier = None
if "--telegram" in sys.argv:
    from load_keys import load_telegram_keys
    from dashboard.telegram.telegram_notifier import TelegramNotifier
    try:
        _bot_token, _chat_id = load_telegram_keys()
        _telegram_notifier = TelegramNotifier(
            bus=bus,
            bot_token=_bot_token,
            chat_id=_chat_id,
            notify_hold=False,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"  WARNING: Telegram disabled — {exc}")

# Optional Alpaca order manager
_use_alpaca = "--alpaca" in sys.argv
if _use_alpaca:
    from load_keys import load_alpaca_keys
    from execution.broker.alpaca_order_manager import AlpacaOrderManager
    _alpaca_api_key, _alpaca_secret_key = load_alpaca_keys()
    alpaca_order_manager = AlpacaOrderManager(
        bus=bus,
        initial_portfolio_value=capital,
        api_key=_alpaca_api_key,
        secret_key=_alpaca_secret_key,
        live_trading=False,           # paper mode by default
    )
    print(f"  Execution:      AlpacaOrderManager (paper mode)")
else:
    print(f"  Execution:      OrderManager (in-memory paper fill)")
```

### Step 2 — Start TelegramNotifier before loop

```python
# Start Telegram bot (after bus and all components wired)
if _telegram_notifier:
    _telegram_notifier.start()
    print(f"  Telegram:       ENABLED (bot polling started)")
```

### Step 3 — Per-cycle portfolio.state publish (end of each symbol loop)

```python
# After all symbols processed each cycle — publish portfolio state for Telegram
from communication.events.portfolio_state_event import PortfolioStateEvent

_pv = tracker.portfolio_value(price_feed)
_pos_list = []
for sym in entry_prices:
    pos = tracker.get_position(sym, price_feed.get(sym, 0.0))
    if pos:
        _pos_list.append({
            "symbol": sym,
            "quantity": pos.quantity,
            "entry_price": pos.avg_entry_price,
        })
bus.publish(PortfolioStateEvent(
    event_type="portfolio.state",
    portfolio_value=_pv,
    cash=tracker.cash,
    realized_pnl=metrics.total_pnl,
    total_return_pct=((_pv - capital) / capital) if capital > 0 else 0.0,
    positions=tuple(_pos_list),
))
```


### Step 4 — Order execution dispatch

```python
# Replace the two order_manager.execute() calls with:
_exec = alpaca_order_manager if _use_alpaca else order_manager

# BUY path:
fill = _exec.execute(order)

# SELL path:
fill = _exec.execute(sell_order)
```

### Step 5 — Session end event and notifier teardown

```python
# After the trading loop, before the final report print:
bus.publish(BaseEvent(
    event_type="session.end",
    payload={
        "total_pnl": m["total_pnl"],
        "win_rate": m["win_rate"],
        "total_trades": m["total_trades"],
        "sharpe_ratio": m["sharpe_ratio"],
        "max_drawdown": m["max_drawdown"],
        "portfolio_value": portfolio_val,
    },
))

# Stop Telegram notifier gracefully
if _telegram_notifier:
    _telegram_notifier.stop()
```

### Step 6 — system.shutdown_requested handler

`run_hour.py` needs to honour the `/stop` command by watching for a `system.shutdown_requested` event. Add after the bus is created:

```python
def _on_shutdown_requested(event: BaseEvent) -> None:
    global shutdown
    print("\n[Telegram /stop] Graceful shutdown requested via bot.")
    shutdown = True

bus.subscribe("system.shutdown_requested", _on_shutdown_requested)
```

### CLI flags summary

```
py -3 run_hour.py                          # unchanged — in-memory paper, no Telegram
py -3 run_hour.py --telegram               # + Telegram alerts, in-memory paper
py -3 run_hour.py --alpaca                 # + Alpaca paper API, no Telegram
py -3 run_hour.py --alpaca --telegram      # full live integration (paper API + Telegram)
py -3 run_hour.py --capital 50000 --minutes 30 --alpaca --telegram
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Reflection

Before finalising the property list, redundancies were eliminated:

- Requirements 1.1 and 1.2 both test `_format_fill_message()`. The SELL formatter is a strict superset of the BUY formatter (it adds P&L). These are kept separate because the P&L field is only present for SELL and its correctness is distinct.
- Requirements 3.2 and 3.3 are mirror properties (suppress vs. send for HOLD). They test opposite sides of the same filter and cannot be merged; both are kept.
- Requirements 6.2 and 6.3 both concern `execute()`. Requirement 6.3 (fill_price equals API average) is a refinement of 6.2 (FillEvent fields are correct) and is folded into a single combined property.
- Requirements 9.1 and 9.2 are independent risk limits with different triggers. Both are kept.
- Requirement 9.5 (peak tracking) is subsumed by requirement 9.2 (drawdown rejection depends on a correctly tracked peak). It is combined into the drawdown property.
- Requirements 10.1 fields check is a structural mapping property. 10.3 (empty list) is an edge case covered by the generator range and not a separate property.


### Property 1: BUY fill message contains all required fields

*For any* `FillEvent` with `action="BUY"`, the formatted message string returned by `_format_fill_message()` SHALL contain the symbol, the quantity rounded to exactly 4 decimal places, the fill price formatted to exactly 2 decimal places, and the UTC timestamp string of the fill.

**Validates: Requirements 1.1**

---

### Property 2: SELL fill message contains all required fields including P&L

*For any* `FillEvent` with `action="SELL"` and any known entry price, the formatted message string returned by `_format_fill_message()` SHALL contain the symbol, the quantity rounded to exactly 4 decimal places, the fill price to exactly 2 decimal places, the realized P&L (computed as `(fill_price - entry_price) * quantity`) formatted to exactly 2 decimal places with a sign prefix, and the UTC timestamp string.

**Validates: Requirements 1.2**

---

### Property 3: Decision digest message contains symbol, action, confidence, and truncated rationale

*For any* `DecisionEvent` with a rationale of arbitrary length, the formatted message string returned by `_format_decision_message()` SHALL contain the symbol, the action, the confidence score formatted to 2 decimal places, and at most the first 200 characters of the rationale — never more.

**Validates: Requirements 3.1**

---

### Property 4: HOLD events are suppressed when notify_hold=False

*For any* `DecisionEvent` with `action="HOLD"` received when the `TelegramNotifier` is configured with `notify_hold=False`, the notifier SHALL NOT invoke `bot.send_message()`.

**Validates: Requirements 3.2**

---

### Property 5: All decision events including HOLD are sent when notify_hold=True

*For any* `DecisionEvent` (BUY, SELL, or HOLD) received when the `TelegramNotifier` is configured with `notify_hold=True`, the notifier SHALL invoke `bot.send_message()` exactly once per event.

**Validates: Requirements 3.3**

---

### Property 6: Session summary message contains all five metric fields correctly formatted

*For any* session end payload with varying `total_pnl`, `win_rate`, `total_trades`, `sharpe_ratio`, and `max_drawdown` values, the formatted summary string returned by `_format_session_summary()` SHALL contain all five metrics with the correct precision: P&L to 2dp with sign, win rate as a percentage to 1dp, trade count as an integer, Sharpe to 4dp, and max drawdown as a percentage to 4dp.

**Validates: Requirements 2.1**

---

### Property 7: /status reply contains portfolio value and cash from latest portfolio.state event

*For any* sequence of `PortfolioStateEvent` publications with varying `portfolio_value` and `cash` fields, a `/status` command issued after the sequence SHALL always reply with the values from the most recently published event, formatted to 2 decimal places.

**Validates: Requirements 4.1**

---

### Property 8: /positions reply lists all positions or reports "No open positions."

*For any* `PortfolioStateEvent` with zero or more positions, a `/positions` command SHALL reply with exactly one line per position (symbol, quantity to 4dp, entry price to 2dp) when positions exist, or with the exact string "No open positions." when the positions list is empty.

**Validates: Requirements 4.2**

---

### Property 9: AlpacaOrderManager execute() produces a correctly populated FillEvent from API response

*For any* valid `Order` (BUY or SELL, any symbol, any quantity ≥ 0.01), when the Alpaca API mock returns an arbitrary average fill price `P`, `execute()` SHALL return a `FillEvent` where `fill_price == P`, `symbol == order.symbol`, `action == order.action`, `quantity == order.quantity`, `event_type == "execution.fill"`, and the event SHALL be published on the EventBus exactly once.

**Validates: Requirements 6.2, 6.3**

---

### Property 10: Orders exceeding 2% of portfolio value are rejected

*For any* `Order` where `order.quantity × current_price > 0.02 × portfolio_value`, `AlpacaOrderManager.execute()` SHALL raise a `ValueError` and SHALL NOT submit the order to the Alpaca API. For any `Order` where `order.quantity × current_price ≤ 0.02 × portfolio_value`, the order SHALL pass the capital check.

**Validates: Requirements 9.1**

---

### Property 11: All orders are rejected when session drawdown exceeds 10%, and drawdown breach event is published

*For any* order received when `(peak_value - current_value) / peak_value > 0.10`, `AlpacaOrderManager.execute()` SHALL raise a `ValueError`, SHALL NOT submit the order to the Alpaca API, and SHALL publish a `risk.drawdown_breach` event on the EventBus. Furthermore, the tracked `peak_value` SHALL always equal the maximum of all portfolio values observed since construction.

**Validates: Requirements 9.2, 9.5**

---

### Property 12: get_positions() maps Alpaca API response to standard dict structure

*For any* Alpaca positions API response containing zero or more position records, `get_positions()` SHALL return a `list[dict]` where every dict contains exactly the keys `"symbol"`, `"quantity"`, and `"market_value"` populated from the corresponding Alpaca position fields.

**Validates: Requirements 10.1, 10.3**

---

### Property 13: TelegramNotifier start()/stop() subscription round-trip

*For any* `TelegramNotifier` instance, calling `start()` followed by `stop()` SHALL leave the EventBus subscription count at the same value it had before `start()` was called — i.e., all four subscriptions added by `start()` are removed by `stop()`.

**Validates: Requirements 5.2, 5.3**


---

## Error Handling

### TelegramNotifier error handling

| Failure point | Behaviour |
|---|---|
| Bot API call fails (`TelegramError`, network) | `_safe_send()` catches the exception, logs at `WARNING` via `self._log.warning()`. If the logger itself raises, the exception propagates up to halt further operation. |
| `bot_token` empty or whitespace at construction | Raises `ValueError("bot_token must not be empty.")` immediately |
| `chat_id` empty or whitespace at construction | Raises `ValueError("chat_id must not be empty.")` immediately |
| EventBus handler raises unexpectedly | Caught and logged at `ERROR` level; does not crash the bot thread |
| Bot thread crashes | Logged at `CRITICAL`; main trading loop continues unaffected (Telegram is non-critical) |
| `/stop` command — EventBus publish fails | Exception is logged; no confirmation reply is sent to prevent false assurance |

### AlpacaOrderManager error handling

| Failure point | Behaviour |
|---|---|
| `ALPACA_API_KEY` or `ALPACA_SECRET_KEY` absent | Raises `ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in keys.env.")` at construction |
| `keys.env` missing or unreadable | Raises `FileNotFoundError` / `IOError` at construction (from `load_alpaca_keys`) |
| `live_trading=True` without `paper_validation_complete=True` | Raises `ValueError("Live trading requires paper_validation_complete=True to confirm 30-day validation has been reviewed.")` before any network call |
| Alpaca API returns HTTP error on `execute()` | Raises `RuntimeError(f"Alpaca API error: {alpaca_error_message}")`. No `FillEvent` is published. |
| Order exceeds 2% capital limit | Raises `ValueError`; logs `WARNING` with symbol, notional, and limit |
| Drawdown > 10% | Raises `ValueError`; logs `WARNING`; publishes `risk.drawdown_breach` event |
| `get_positions()` or `get_portfolio_value()` API error | Raises `RuntimeError` with Alpaca error message |
| Order submitted but fill confirmation times out | Raises `RuntimeError("Alpaca fill timeout for order {order_id}")` |

---

## Testing Strategy

### Property-based testing

The project uses `hypothesis` (already in `requirements-dev.txt` or to be added). Each property test runs a minimum of 100 iterations.

Tag format: `# Feature: telegram-alpaca-integration, Property N: <property_text>`

**Properties mapped to tests:**

| Property | Test location | Hypothesis strategy |
|---|---|---|
| P1 – BUY fill message fields | `src/dashboard/telegram/tests/test_telegram_notifier_props.py` | `st.builds(FillEvent, action=st.just("BUY"), ...)` |
| P2 – SELL fill message fields | same | `st.builds(FillEvent, action=st.just("SELL"), ...)` + `st.floats()` for entry price |
| P3 – Decision digest truncation | same | `st.builds(DecisionEvent, rationale=st.text(min_size=0, max_size=500))` |
| P4 – HOLD suppressed | same | `st.builds(DecisionEvent, action=st.just("HOLD"))` |
| P5 – HOLD sent when notify_hold=True | same | `st.builds(DecisionEvent, action=st.just("HOLD"))` |
| P6 – Session summary fields | same | `st.fixed_dictionaries(...)` with floats for each metric |
| P7 – /status reply latest state | same | `st.lists(st.builds(PortfolioStateEvent, ...), min_size=1)` |
| P8 – /positions reply | same | `st.lists(st.fixed_dictionaries(...), max_size=20)` |
| P9 – execute() FillEvent correctness | `src/execution/broker/tests/test_alpaca_order_manager_props.py` | `st.builds(Order)` + mock Alpaca returning random fill price |
| P10 – 2% capital limit | same | `st.floats(min_value=0.01)` for quantity and price; portfolio value varied |
| P11 – drawdown rejection + peak tracking | same | `st.lists(st.floats(min_value=1.0), min_size=2)` for portfolio value sequence |
| P12 – get_positions() mapping | same | `st.lists(st.fixed_dictionaries(...))` of mock Alpaca position dicts |
| P13 – start/stop subscription round-trip | `src/dashboard/telegram/tests/test_telegram_notifier_props.py` | No generation needed; pure lifecycle test; still run ≥100 times via `@settings(max_examples=100)` on a parameterized fixture |

### Example-based unit tests

| What | Test file | Purpose |
|---|---|---|
| Bot API failure → WARNING log | `test_telegram_notifier_unit.py` | Verify logging on Telegram error |
| `/stop` publishes shutdown event before reply | same | Ordering assertion with mocked bus and bot |
| Unknown command → help reply | same | Verify help text contains all four command names |
| Alpaca API error on execute() → RuntimeError, no FillEvent | `test_alpaca_order_manager_unit.py` | Error path |
| live_trading=True + paper_validation_complete=False → ValueError | same | Live gate enforcement |
| paper mode → INFO log with paper API URL | same | Constructor log |
| bot_token / chat_id empty → ValueError | same | Input validation |
| ALPACA_API_KEY missing → ValueError | same | Credential validation |

### Architecture compliance (CI smoke test)

`scripts/architecture_lint.py` runs in the existing GitHub Actions workflow (`.github/workflows/python-ci.yml`). Both new components must produce zero violations. No new CI configuration is required.

### Integration notes

`AlpacaOrderManager` tests mock the `alpaca-py` `TradingClient` at the class level using `unittest.mock.patch`. No real API calls are made during tests. A separate manual validation step (`run_hour.py --alpaca`) is used for end-to-end paper trading validation.

