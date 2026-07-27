"""
Immutable subscription model for the Communication Layer.

A Subscription represents an immutable registration describing a
consumer's interest in one or more events. The model contains only
declarative data and performs no routing, filtering, or EventBus logic.

This model is:

- Immutable
- Thread-safe
- Transport independent
- Deterministically serializable
- Suitable for use as a dictionary key

Python Version:
    3.13+
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .event_priority import EventPriority


@dataclass(frozen=True, slots=True)
class Subscription:
    """Immutable event subscription.

    Attributes:
        subscriber_id:
            Globally unique identifier of the subscriber.

        event_pattern:
            Canonical event name or event pattern.

            Examples:
                "market.data.received"
                "execution.order.*"
                "risk.*"

        priority:
            Dispatch priority assigned to this subscription.

        enabled:
            Indicates whether the subscription is active.

        filter_expression:
            Optional implementation-neutral filtering expression.

            This value is intentionally opaque to the Communication
            Layer and reserved for future filtering implementations.
    """

    subscriber_id: str
    event_pattern: str
    priority: EventPriority = EventPriority.NORMAL
    enabled: bool = True
    filter_expression: str | None = None

    # ------------------------------------------------------------------
    # Internal validation constants
    # ------------------------------------------------------------------

    _MAX_ID_LENGTH: ClassVar[int] = 255
    _MAX_PATTERN_LENGTH: ClassVar[int] = 255

    def __post_init__(self) -> None:
        """Validate the immutable subscription."""

        self._validate_subscriber_id()
        self._validate_event_pattern()
        self._validate_filter_expression()

    def _validate_subscriber_id(self) -> None:
        """Validate subscriber_id."""
        value = self.subscriber_id.strip()

        if not value:
            raise ValueError("subscriber_id must not be empty.")

        if len(value) > self._MAX_ID_LENGTH:
            raise ValueError("subscriber_id exceeds maximum length.")

    def _validate_event_pattern(self) -> None:
        """Validate event_pattern."""
        pattern = self.event_pattern.strip()

        if not pattern:
            raise ValueError("event_pattern must not be empty.")

        if len(pattern) > self._MAX_PATTERN_LENGTH:
            raise ValueError("event_pattern exceeds maximum length.")

        if " " in pattern:
            raise ValueError("event_pattern must not contain whitespace.")

        if ".." in pattern:
            raise ValueError("event_pattern contains invalid separators.")

    def _validate_filter_expression(self) -> None:
        """Validate the optional filter expression."""
        if self.filter_expression is None:
            return

        if not self.filter_expression.strip():
            raise ValueError("filter_expression cannot be empty.")

    @property
    def is_enabled(self) -> bool:
        """Return whether this subscription is enabled."""
        return self.enabled

    @property
    def has_filter(self) -> bool:
        """Return whether a filter expression is configured."""
        return self.filter_expression is not None

    def matches_exact(self, event_name: str) -> bool:
        """Perform an exact event-name comparison.

        Wildcard interpretation intentionally belongs to the future
        EventBus implementation and is therefore outside the scope of
        this immutable model.

        Args:
            event_name:
                Canonical event name.

        Returns:
            True if the supplied event name exactly matches the stored
            event pattern.
        """
        return self.event_pattern == event_name

    def to_dict(self) -> dict[str, object]:
        """Serialize the subscription deterministically.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "subscriber_id": self.subscriber_id,
            "event_pattern": self.event_pattern,
            "priority": self.priority.value,
            "enabled": self.enabled,
            "filter_expression": self.filter_expression,
        }

    def __str__(self) -> str:
        """Return a concise human-readable representation."""
        status = "enabled" if self.enabled else "disabled"

        return (
            "Subscription("
            f"subscriber='{self.subscriber_id}', "
            f"pattern='{self.event_pattern}', "
            f"priority='{self.priority}', "
            f"status='{status}')"
        )
