"""
dashboard.web.dashboard_state
================================

DashboardState — thread-safe in-memory state feeding the web dashboard.

Populated two ways:
  1. Event-driven: subscribed to the EventBus for DecisionEvent and
     FillEvent (same pattern as the terminal LiveView) — zero imports
     from execution/intelligence internals, only the _EventLike Protocol.
  2. Direct push: MetricsEngine/Portfolio in this repo are pull-based
     (no events published), so run_hour.py calls update_metrics()/
     update_positions() once per cycle.

Flask request handlers (running on Flask's own threads) read via
snapshot(); the EventBus dispatch thread and run_hour.py's main loop
write via record_event()/update_metrics()/update_positions(). All
access is guarded by a single lock.

Python Version: 3.11+
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Protocol


class _EventLike(Protocol):
    """Structural type for anything record_event can accept.

    Deliberately a Protocol rather than importing foundation.BaseEvent:
    this module only ever needs duck-typed access (event_type, to_dict(),
    optional symbol/action/etc.), so it shouldn't require callers to
    construct a real BaseEvent subclass - matching the existing rule
    that this layer has zero import-time coupling to other layers.
    """

    @property
    def event_type(self) -> str: ...

    def to_dict(self) -> dict[str, Any]: ...


_MAX_RECENT_EVENTS = 200
_MAX_RECENT_FILLS = 100


class DashboardState:
    """Thread-safe snapshot store for the web dashboard."""

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

    # ------------------------------------------------------------------
    # Writers
    # ------------------------------------------------------------------

    def record_event(self, event: _EventLike) -> None:
        """EventBus handler: record any event to the raw feed, and
        additionally index DecisionEvent/FillEvent for the summary
        views if the event carries those fields.
        """
        with self._lock:
            data = event.to_dict()
            self._recent_events.append(data)

            # DecisionEvent and FillEvent both carry a 'symbol' field;
            # duck-type rather than importing their classes, to keep
            # this module free of intelligence/execution imports.
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
        """Push the latest metrics snapshot (pull-based, called once per cycle)."""
        with self._lock:
            self._metrics = dict(metrics)

    def update_positions(self, positions: dict[str, tuple[float, float]]) -> None:
        """Push the latest positions snapshot: symbol -> (quantity, avg_price)."""
        with self._lock:
            self._positions = {
                sym: {"quantity": qty, "avg_price": avg_price}
                for sym, (qty, avg_price) in positions.items()
            }

    def tick(self, cycle: int) -> None:
        """Record that a new cycle has started (drives the 'last update' clock)."""
        with self._lock:
            self._cycle = cycle
            self._last_update = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Reader (Flask request handlers)
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return a fully JSON-serializable snapshot of current state."""
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
