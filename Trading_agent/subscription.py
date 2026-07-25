"""
communication.models.subscription
=================================

Defines the immutable subscription contract used by the Communication
Layer.

A Subscription describes a consumer's interest in one or more events.
It is a pure data model and contains no EventBus, routing, filtering,
or execution logic.

This model is intentionally transport-independent and thread-safe.

Python Version:
    3.13+
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .event_priority import EventPriority


@dataclass(frozen=True, slots=True)
class Subscription:
    """Immutable subscription descriptor.

    A Subscription uniquely identifies a consumer registration within
    the Communication Layer.

    Attributes:
        subscriber_id:
            Globally unique identifier for the subscriber.

        event_pattern:
            Canonical event name or pattern.

            Examples:
                "market.data.received"
                "execution.order.*"
                "risk.*"

        priority:
            Dispatch priority assigned to this subscription.

            This controls subscriber execution order when multiple
            subscribers receive the same event.

        enabled:
            Indicates whether the subscription is active.

        filter_expression:
            Optional implementation-neutral filter expression reserved
            for future event filtering capabilities.

            The Communication Layer treats this value as opaque data.
    """

    subscriber_id: str
    event_pattern: str
    priority: EventPriority = EventPriority.NORMAL
    enabled: bool = True
    filter_expression: str | None = None

    _MAX_ID_LENGTH: Final[int] = 255
    _MAX_PATTERN_LENGTH: Final[int] = 255

    def __post_init__(self) -> None:
        """Validate the subscription.

        Raises:
            ValueError:
                If any public field contains an invalid value.
        """
        if not self.subscriber_id.strip():
            raise ValueError("subscriber_id must not be empty.")

        if len(self.subscriber_id) > self._MAX_ID_LENGTH:
            raise ValueError(
                "subscriber_id exceeds maximum length."
            )

        if not self.event_pattern.strip():
            raise ValueError("event_pattern must not be empty.")

        if len(self.event_pattern) > self._MAX_PATTERN_LENGTH:
            raise ValueError(
                "event_pattern exceeds maximum length."
            )

        if " " in self.event_pattern:
            raise ValueError(
                "event_pattern must not contain whitespace."
            )

        if ".." in self.event_pattern:
            raise ValueError(
                "event_pattern contains an invalid separator."
            )

    @property
    def is_enabled(self) -> bool:
        """Return whether this subscription is active.

        Returns:
            True if enabled; otherwise False.
        """
        return self.enabled

    @property
    def has_filter(self) -> bool:
        """Return whether a filter expression is configured.

        Returns:
            True if a filter expression exists.
        """
        return (
            self.filter_expression is not None
            and self.filter_expression.strip() != ""
        )

    def matches_exact(self, event_name: str) -> bool:
        """Determine whether the supplied event exactly matches.

        This helper performs only an exact string comparison.
        Wildcard interpretation belongs to the future EventBus
        implementation and is intentionally excluded from this model.

        Args:
            event_name:
                Canonical event name.

        Returns:
            True if the names are identical.
        """
        return self.event_pattern == event_name

    def __str__(self) -> str:
        """Return a readable representation."""
        status = "enabled" if self.enabled else "disabled"

        return (
            f"Subscription("
            f"subscriber='{self.subscriber_id}', "
            f"pattern='{self.event_pattern}', "
            f"priority='{self.priority}', "
            f"status='{status}')"
        )