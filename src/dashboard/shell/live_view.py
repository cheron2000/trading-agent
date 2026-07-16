"""
dashboard.shell.live_view
===========================

LiveView — terminal-based read-only dashboard.

Subscribes to events via the EventBus and renders live system state
to stdout. Zero write-paths into other layers — it only subscribes.

This is the first Dashboard milestone (shell/CLI). A web GUI is an
optional later milestone outside current scope.

Python Version: 3.11+
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import ClassVar

from foundation.base_event import BaseEvent
from communication.interfaces.i_event_bus import IEventBus
from communication.models.subscription import Subscription


class LiveView:
    """Terminal dashboard that renders system events in real time.

    Subscribes to the EventBus for selected event patterns and prints
    formatted summaries to stdout (or an injected output stream for
    testing). No state mutations outside its own display buffer.

    Architecture rule enforced: ZERO imports from execution, intelligence,
    data, or analytics internals. All data arrives via events.
    """

    _SUBSCRIBED_PATTERNS: ClassVar[tuple[str, ...]] = (
        "data.feature_vector",
        "intelligence.decision",
        "execution.fill",
        "health.heartbeat.recorded",
    )

    def __init__(
        self,
        bus: IEventBus,
        output=None,
    ) -> None:
        """
        Args:
            bus:    EventBus to subscribe on.
            output: Output stream (defaults to sys.stdout). Inject a
                    StringIO for testing.
        """
        self._bus = bus
        self._output = output or sys.stdout
        self._subscriptions: list[Subscription] = []
        self._event_count: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Subscribe to all tracked event patterns."""
        for pattern in self._SUBSCRIBED_PATTERNS:
            sub = self._bus.subscribe(pattern, self._handle_event)
            self._subscriptions.append(sub)
        self._print("LiveView started. Listening for events...")

    def stop(self) -> None:
        """Unsubscribe from all patterns."""
        for sub in self._subscriptions:
            self._bus.unsubscribe(sub)
        self._subscriptions.clear()
        self._print("LiveView stopped.")

    # ------------------------------------------------------------------
    # Event handler — READ ONLY
    # ------------------------------------------------------------------

    def _handle_event(self, event: BaseEvent) -> None:
        """Render an incoming event to the output stream."""
        self._event_count += 1
        now = datetime.now(timezone.utc).isoformat()
        line = (
            f"[{now}] #{self._event_count:04d} "
            f"{event.event_type:<35} id={event.event_id[:8]}"
        )
        self._print(line)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _print(self, message: str) -> None:
        print(message, file=self._output, flush=True)

    @property
    def event_count(self) -> int:
        """Return total events received since start."""
        return self._event_count
