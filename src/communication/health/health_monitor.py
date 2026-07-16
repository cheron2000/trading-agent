"""
communication.health.health_monitor
=====================================

Concrete HealthMonitor implementation for the Communication Layer.

Implements the IHealthMonitor Protocol. Tracks component liveness
based on received Heartbeat signals and a configurable time window.

Design constraints:
- No imports from layers above Communication.
- Thread-safe via threading.Lock.
- Optionally publishes events on an IEventBus when heartbeats are recorded.

Python Version: 3.11+
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import ClassVar

from foundation.base_event import BaseEvent
from communication.models.heartbeat import Heartbeat
from communication.interfaces.i_event_bus import IEventBus
from communication.interfaces.i_health_monitor import IHealthMonitor


class HealthMonitor:
    """Tracks component liveness via Heartbeat signals.

    Implements ``IHealthMonitor``. A component is considered alive when:
      1. It has been registered (explicitly or via auto-registration).
      2. Its most recent ``Heartbeat.health_state.is_operational`` is True.
      3. Its most recent ``Heartbeat.last_seen`` is within
         ``liveness_window_seconds`` of the current UTC time.

    An optional ``IEventBus`` may be supplied at construction time.
    When provided, a ``BaseEvent(event_type="health.heartbeat.recorded")``
    is published each time a heartbeat is recorded.

    Thread safety is ensured via a single ``threading.Lock``.
    """

    DEFAULT_LIVENESS_WINDOW_SECONDS: ClassVar[int] = 30

    def __init__(
        self,
        liveness_window_seconds: float = DEFAULT_LIVENESS_WINDOW_SECONDS,
        event_bus: IEventBus | None = None,
    ) -> None:
        """Initialise the health monitor.

        Args:
            liveness_window_seconds:
                Maximum age (in seconds) of the last heartbeat for a
                component to be considered alive. Must be > 0.
                Defaults to 30 seconds.
            event_bus:
                Optional event bus. When provided, a heartbeat-recorded
                event is published on every ``record_heartbeat`` call.

        Raises:
            ValueError: If ``liveness_window_seconds`` is zero or negative.
        """
        if liveness_window_seconds <= 0:
            raise ValueError(
                "liveness_window_seconds must be greater than zero."
            )

        self._liveness_window = liveness_window_seconds
        self._event_bus = event_bus
        self._lock = threading.Lock()
        # component_name → latest Heartbeat
        self._heartbeats: dict[str, Heartbeat] = {}
        # component_name → registered flag
        self._registered: set[str] = set()

    # ------------------------------------------------------------------
    # IHealthMonitor implementation
    # ------------------------------------------------------------------

    def register(self, component_name: str) -> None:
        """Register a component for health monitoring.

        No-op if the component is already registered.

        Args:
            component_name: Unique name of the component. Must not be empty.

        Raises:
            ValueError: If ``component_name`` is empty or blank.
        """
        if not component_name or not component_name.strip():
            raise ValueError("component_name must not be empty.")

        with self._lock:
            self._registered.add(component_name.strip())

    def record_heartbeat(self, heartbeat: Heartbeat) -> None:
        """Record a heartbeat signal from a component.

        Stores the latest heartbeat and auto-registers the component
        if it has not been explicitly registered. Optionally publishes
        a ``health.heartbeat.recorded`` event on the configured bus.

        Args:
            heartbeat: Immutable Heartbeat from the component.

        Raises:
            ValueError: If ``heartbeat`` is None.
        """
        if heartbeat is None:
            raise ValueError("heartbeat must not be None.")

        component = heartbeat.component_name.strip()

        with self._lock:
            # Auto-register if not already known
            self._registered.add(component)
            self._heartbeats[component] = heartbeat

        # Publish event outside the lock to avoid potential deadlock
        if self._event_bus is not None:
            event = BaseEvent(event_type="health.heartbeat.recorded")
            self._event_bus.publish(event)

    def is_alive(self, component_name: str) -> bool:
        """Return whether a component is currently alive.

        A component is alive when all three conditions hold:
          1. It is registered.
          2. Its last heartbeat ``health_state.is_operational`` is True.
          3. Its last heartbeat ``last_seen`` is within the liveness window.

        Args:
            component_name: Name of the component to query.

        Returns:
            True if alive, False otherwise (unknown, expired, or unhealthy).
        """
        with self._lock:
            if component_name not in self._registered:
                return False

            heartbeat = self._heartbeats.get(component_name)

        if heartbeat is None:
            return False

        if not heartbeat.health_state.is_operational:
            return False

        now = datetime.now(timezone.utc)
        last_seen = heartbeat.last_seen
        # Ensure timezone-aware comparison
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)

        age_seconds = (now - last_seen).total_seconds()
        return age_seconds <= self._liveness_window

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def registered_components(self) -> frozenset[str]:
        """Return all registered component names."""
        with self._lock:
            return frozenset(self._registered)

    def get_heartbeat(self, component_name: str) -> Heartbeat | None:
        """Return the latest heartbeat for a component, or None."""
        with self._lock:
            return self._heartbeats.get(component_name)


# Runtime protocol check
assert isinstance(HealthMonitor(), IHealthMonitor), (
    "HealthMonitor does not satisfy the IHealthMonitor Protocol."
)
