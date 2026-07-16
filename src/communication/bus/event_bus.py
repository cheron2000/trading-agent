"""
communication.bus.event_bus
============================

Concrete in-memory, thread-safe EventBus implementation.

Implements the IEventBus Protocol. All cross-layer event delivery
within the AI Trading OS goes through this component.

Design constraints:
- No imports from layers above Communication.
- Synchronous dispatch only in this version.
- Pattern matching via fnmatch (supports wildcards: * and ?).

Python Version: 3.11+
"""

from __future__ import annotations

import fnmatch
import threading
from typing import Callable
from uuid import uuid4

from foundation.base_event import BaseEvent
from communication.models.event_priority import EventPriority
from communication.models.event_metadata import EventMetadata
from communication.models.subscription import Subscription
from communication.interfaces.i_event_bus import IEventBus


class EventBus:
    """Thread-safe in-memory publish/subscribe event bus.

    Implements ``IEventBus``. Subscribers register handlers for
    event name patterns; publishers dispatch events to all matching
    enabled handlers synchronously.

    Pattern matching uses ``fnmatch`` semantics:
        - ``"market.tick"``   — exact match
        - ``"market.*"``      — any single segment after ``market.``
        - ``"*"``             — matches every event type

    Thread safety is ensured via a single reentrant lock (``RLock``).
    All public methods acquire the lock before reading or mutating
    internal state.
    """

    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()
        # Maps subscriber_id → (Subscription, handler)
        self._subscriptions: dict[
            str, tuple[Subscription, Callable[[BaseEvent], None]]
        ] = {}

    # ------------------------------------------------------------------
    # IEventBus implementation
    # ------------------------------------------------------------------

    def publish(self, event: BaseEvent) -> None:
        """Publish an event to all matching subscribers.

        Dispatches synchronously to every handler whose subscription
        pattern matches ``event.event_type`` and whose subscription
        is enabled.

        Args:
            event: Immutable Foundation event to publish.

        Raises:
            ValueError: If ``event`` is None.
        """
        if event is None:
            raise ValueError("event must not be None.")

        with self._lock:
            matching = [
                handler
                for sub, handler in self._subscriptions.values()
                if sub.enabled
                and fnmatch.fnmatch(event.event_type, sub.event_pattern)
            ]

        # Invoke handlers outside the lock to prevent deadlocks
        # if a handler calls publish/subscribe recursively.
        for handler in matching:
            handler(event)

    def subscribe(
        self,
        event_pattern: str,
        handler: Callable[[BaseEvent], None],
    ) -> Subscription:
        """Register a handler for events matching ``event_pattern``.

        Args:
            event_pattern:
                fnmatch-style event name pattern. Must not be empty
                or contain whitespace.
            handler:
                Callable invoked with each matching event.

        Returns:
            Immutable ``Subscription`` descriptor.

        Raises:
            ValueError: If ``event_pattern`` is empty.
        """
        if not event_pattern or not event_pattern.strip():
            raise ValueError("event_pattern must not be empty.")

        subscriber_id = str(uuid4())
        subscription = Subscription(
            subscriber_id=subscriber_id,
            event_pattern=event_pattern,
            priority=EventPriority.NORMAL,
            enabled=True,
        )

        with self._lock:
            self._subscriptions[subscriber_id] = (subscription, handler)

        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        """Cancel a subscription. No-op if not found.

        Args:
            subscription: The ``Subscription`` to cancel.
        """
        with self._lock:
            self._subscriptions.pop(subscription.subscriber_id, None)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def subscription_count(self) -> int:
        """Return the number of active subscriptions."""
        with self._lock:
            return len(self._subscriptions)

    def clear(self) -> None:
        """Remove all subscriptions. Intended for testing/teardown."""
        with self._lock:
            self._subscriptions.clear()


# Runtime protocol check — ensures EventBus satisfies IEventBus.
assert isinstance(EventBus(), IEventBus), (
    "EventBus does not satisfy the IEventBus Protocol."
)
