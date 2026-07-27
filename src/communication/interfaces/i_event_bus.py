"""
communication.interfaces.i_event_bus
=====================================

Defines the IEventBus Protocol for the Communication Layer.

This interface specifies the contract that all EventBus implementations
must satisfy. It is intentionally free of implementation logic.

All cross-layer event exchange must go through an IEventBus — never
via direct imports across layer boundaries.

Python Version: 3.11+
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from communication.models.subscription import Subscription
from foundation.base_event import BaseEvent


@runtime_checkable
class IEventBus(Protocol):
    """Protocol defining the EventBus contract.

    Implementations provide in-process or distributed pub/sub.
    Callers depend only on this interface, never on a concrete class.

    All methods are synchronous in this version. Async variants
    are deferred to a future module revision.
    """

    def publish(self, event: BaseEvent) -> None:
        """Publish an event to all matching subscribers.

        The event is dispatched to every handler whose subscription
        pattern matches the event's ``event_type``.

        Args:
            event:
                Immutable Foundation event to publish. Must not be None.

        Raises:
            ValueError:
                If ``event`` is None.
        """
        ...

    def subscribe(
        self,
        event_pattern: str,
        handler: Callable[[BaseEvent], None],
    ) -> Subscription:
        """Register a handler for events matching the given pattern.

        Pattern matching semantics (e.g. wildcards) are defined by
        the concrete implementation.

        Args:
            event_pattern:
                Canonical event name or glob-style pattern.
                Examples: ``"market.data.received"``, ``"execution.*"``

            handler:
                Callable invoked when a matching event is published.
                Must accept a single ``BaseEvent`` argument.

        Returns:
            An immutable ``Subscription`` descriptor that can be used
            to cancel the registration via ``unsubscribe``.

        Raises:
            ValueError:
                If ``event_pattern`` is empty or invalid.
        """
        ...

    def unsubscribe(self, subscription: Subscription) -> None:
        """Cancel a previously registered subscription.

        After this call the handler will no longer receive events.
        Calling ``unsubscribe`` with an unknown or already-cancelled
        subscription is a no-op.

        Args:
            subscription:
                The ``Subscription`` descriptor returned by a prior
                ``subscribe`` call.
        """
        ...
