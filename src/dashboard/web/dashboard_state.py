"""
dashboard.web.dashboard_state
================================

Thread-safe state store for the web dashboard.

Dual interface:
  - Module-level singleton API  (used by run_hour.py and the control
    endpoints): set_running(), update_portfolio(), push_trade(),
    push_decision(), push_warning(), push_news(), push_key_status(),
    pop_manual_tick(), is_kill_requested(), snapshot()
  - Class-based DashboardState   (used by unit tests in
    test_dashboard_web.py and any caller that wants an isolated
    instance): record_event(), update_metrics(), update_positions(),
    tick(), snapshot()

Both APIs are fully thread-safe.

Python Version: 3.11+
"""

from __future__ import annotations

import queue
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

from foundation.base_event import BaseEvent

_MAX_RECENT_EVENTS = 200
_MAX_RECENT_FILLS = 100
_MAX_TRADES = 200
_MAX_DECISIONS = 100
_MAX_WARNINGS = 100
_MAX_CHART_POINTS = 120  # 2 hours at 1-min cycles


# ---------------------------------------------------------------------------
# Class-based API (used by unit tests and isolated callers)
# ---------------------------------------------------------------------------


class DashboardState:
    """Thread-safe, instance-level snapshot store."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = datetime.now(timezone.utc)
        self._recent_events: deque[dict[str, Any]] = deque(maxlen=_MAX_RECENT_EVENTS)
        self._latest_decisions: dict[str, dict[str, Any]] = {}
        self._recent_fills: deque[dict[str, Any]] = deque(maxlen=_MAX_RECENT_FILLS)
        self._metrics: dict[str, Any] = {}
        self._positions: dict[str, Any] = {}
        self._cycle: int = 0
        self._last_update: datetime | None = None

    # Writers

    def record_event(self, event: BaseEvent) -> None:
        with self._lock:
            data = event.to_dict()
            self._recent_events.append(data)
            symbol = getattr(event, "symbol", None)
            action = getattr(event, "action", None)
            if symbol and event.event_type.startswith("intelligence.decision"):
                entry = dict(data)
                entry["confidence"] = getattr(event, "confidence", None)
                entry["symbol"] = symbol
                entry["action"] = action
                self._latest_decisions[symbol] = entry
            elif symbol and event.event_type.startswith("execution.fill"):
                entry = dict(data)
                entry["symbol"] = symbol
                entry["action"] = action
                entry["quantity"] = getattr(event, "quantity", None)
                entry["fill_price"] = getattr(event, "fill_price", None)
                self._recent_fills.append(entry)

    def update_metrics(self, metrics: dict[str, Any]) -> None:
        with self._lock:
            self._metrics = dict(metrics)

    def update_positions(self, positions: dict[str, tuple[float, float]]) -> None:
        with self._lock:
            self._positions = {
                sym: {"quantity": qty, "avg_price": avg_price}
                for sym, (qty, avg_price) in positions.items()
            }

    def tick(self, cycle: int) -> None:
        with self._lock:
            self._cycle = cycle
            self._last_update = datetime.now(timezone.utc)

    # Reader

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "started_at": self._started_at.isoformat(),
                "last_update": (
                    self._last_update.isoformat() if self._last_update else None
                ),
                "cycle": self._cycle,
                "metrics": dict(self._metrics),
                "positions": dict(self._positions),
                "latest_decisions": dict(self._latest_decisions),
                "recent_fills": list(self._recent_fills)[-25:][::-1],
                "recent_events": list(self._recent_events)[-50:][::-1],
                "event_count": len(self._recent_events),
            }


# ---------------------------------------------------------------------------
# Module-level singleton API (used by run_hour.py + Flask control endpoints)
# ---------------------------------------------------------------------------

_lock = threading.Lock()

# Session meta
_running: bool = False
_kill_requested: bool = False
_strategy_mode: str = "SIMPLE-RULE"
_started_at: datetime | None = None
_cycle: int = 0
_uptime_seconds: int = 0

# Portfolio
_portfolio_value: float = 0.0
_cash: float = 0.0
_total_pnl: float = 0.0
_total_return: float = 0.0
_win_rate: float = 0.0
_sharpe_ratio: float = 0.0
_max_drawdown: float = 0.0
_total_trades: int = 0
_initial_capital: float = 100_000.0

# Lists / maps
_positions: list[dict[str, Any]] = []
_trades: deque[dict[str, Any]] = deque(maxlen=_MAX_TRADES)
_decisions: deque[dict[str, Any]] = deque(maxlen=_MAX_DECISIONS)
_warnings: deque[dict[str, Any]] = deque(maxlen=_MAX_WARNINGS)
_news: dict[str, str] = {}
_chart_history: deque[dict[str, Any]] = deque(maxlen=_MAX_CHART_POINTS)
_key_status: dict[str, Any] = {}

# Control flags
_manual_tick_pending: bool = False

# SSE subscriber queues
_sse_subscribers: list[queue.SimpleQueue[str]] = []


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def set_running(
    running: bool, capital: float = 100_000.0, symbols: list[str] | None = None
) -> None:
    global _running, _initial_capital, _cash, _portfolio_value, _started_at
    with _lock:
        _running = running
        if running:
            _initial_capital = capital
            _cash = capital
            _portfolio_value = capital
            _started_at = datetime.now(timezone.utc)
            _warnings.clear()
            _decisions.clear()


def set_stopped() -> None:
    global _running
    with _lock:
        _running = False


def update_portfolio(
    portfolio_value: float,
    cash: float,
    positions: list[dict[str, Any]],
    total_pnl: float,
    total_return: float,
    win_rate: float = 0.0,
    sharpe_ratio: float = 0.0,
    max_drawdown: float = 0.0,
    total_trades: int = 0,
    cycle: int = 0,
) -> None:
    global _portfolio_value, _cash, _positions, _total_pnl, _total_return
    global _win_rate, _sharpe_ratio, _max_drawdown, _total_trades, _cycle, _uptime_seconds
    with _lock:
        _portfolio_value = portfolio_value
        _cash = cash
        _positions = list(positions)
        _total_pnl = total_pnl
        _total_return = total_return
        _win_rate = win_rate
        _sharpe_ratio = sharpe_ratio
        _max_drawdown = max_drawdown
        _total_trades = total_trades
        _cycle = cycle
        if _started_at:
            _uptime_seconds = int(
                (datetime.now(timezone.utc) - _started_at).total_seconds()
            )
        # Append to chart history
        _chart_history.append(
            {
                "ts": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                "cycle": cycle,
                "portfolio_value": portfolio_value,
                "total_pnl": total_pnl,
            }
        )
    _broadcast_snapshot()


def push_trade(
    ts: str,
    symbol: str,
    action: str,
    quantity: float,
    fill_price: float,
    pnl: float | None = None,
) -> None:
    with _lock:
        _trades.appendleft(
            {
                "ts": ts,
                "symbol": symbol,
                "action": action,
                "quantity": quantity,
                "fill_price": fill_price,
                "pnl": pnl,
            }
        )
    _broadcast_snapshot()


def push_decision(
    symbol: str,
    action: str,
    confidence: float,
    rationale: str,
) -> None:
    with _lock:
        existing_idx = next(
            (i for i, d in enumerate(_decisions) if d.get("symbol") == symbol), None
        )
        if existing_idx is not None:
            items = list(_decisions)
            items.pop(existing_idx)
            _decisions.clear()
            _decisions.extend(items)
        _decisions.appendleft(
            {
                "symbol": symbol,
                "action": action,
                "confidence": confidence,
                "rationale": rationale,
            }
        )
    _broadcast_snapshot()


def push_warning(source: str, message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    with _lock:
        _warnings.appendleft({"ts": ts, "source": source, "message": message})
    _broadcast_snapshot()


def push_news(symbol: str, text: str) -> None:
    with _lock:
        _news[symbol] = text
    _broadcast_snapshot()


def push_key_status(key_status: dict[str, Any]) -> None:
    """Push current Groq key rotation status."""
    global _key_status
    with _lock:
        _key_status = dict(key_status)
    _broadcast_snapshot()


# ---------------------------------------------------------------------------
# Control
# ---------------------------------------------------------------------------


def pop_manual_tick() -> bool:
    global _manual_tick_pending
    with _lock:
        result = _manual_tick_pending
        _manual_tick_pending = False
        return result


def request_manual_tick() -> None:
    global _manual_tick_pending
    with _lock:
        _manual_tick_pending = True


def request_kill() -> None:
    global _kill_requested, _running
    with _lock:
        _kill_requested = True
        _running = False
    _broadcast_snapshot()


def is_kill_requested() -> bool:
    with _lock:
        return _kill_requested


def set_strategy_mode(mode: str) -> None:
    global _strategy_mode
    with _lock:
        _strategy_mode = mode


def get_strategy_mode() -> str:
    with _lock:
        return _strategy_mode


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------


def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "running": _running,
            "kill_requested": _kill_requested,
            "strategy_mode": _strategy_mode,
            "cycle": _cycle,
            "uptime_seconds": _uptime_seconds,
            "initial_capital": _initial_capital,
            "portfolio_value": _portfolio_value,
            "cash": _cash,
            "total_pnl": _total_pnl,
            "total_return": _total_return,
            "win_rate": _win_rate,
            "sharpe_ratio": _sharpe_ratio,
            "max_drawdown": _max_drawdown,
            "total_trades": _total_trades,
            "positions": list(_positions),
            "trades": list(_trades),
            "decisions": list(_decisions),
            "warnings": list(_warnings),
            "news": dict(_news),
            "chart_history": list(_chart_history),
            "key_status": dict(_key_status),
        }


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def subscribe_sse() -> queue.SimpleQueue[str]:
    """Register a new SSE subscriber and return its queue."""
    q: queue.SimpleQueue[str] = queue.SimpleQueue()
    with _lock:
        _sse_subscribers.append(q)
    return q


def unsubscribe_sse(q: queue.SimpleQueue[str]) -> None:
    with _lock:
        try:
            _sse_subscribers.remove(q)
        except ValueError:
            pass


def _broadcast_snapshot() -> None:
    """Push the current snapshot to all SSE subscribers (non-blocking)."""
    import json

    msg = json.dumps({"type": "snapshot", "data": snapshot()})
    with _lock:
        subs = list(_sse_subscribers)
    for q in subs:
        try:
            q.put_nowait(msg)
        except Exception:
            pass
