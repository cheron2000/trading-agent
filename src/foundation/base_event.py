"""
Defines the immutable BaseEvent contract for the AI Trading Operating System.

All events exchanged within the system must inherit from BaseEvent.
The class is immutable, fully typed, and suitable for serialization,
auditing, and event-driven communication.

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True, kw_only=True)
class BaseEvent:
    """Base class for all events in the system.

    Every event has a unique identifier, creation timestamp,
    schema version, and event type. Derived event classes may
    extend this class with additional immutable fields.

    Attributes:
        event_id: Globally unique event identifier.
        event_type: Canonical event type name.
        occurred_at: UTC timestamp when the event was created.
        schema_version: Event schema version.
        correlation_id: Optional correlation identifier for tracing.
        causation_id: Optional identifier of the event that caused this event.
    """

    event_type: str

    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    schema_version: str = "1.0"

    correlation_id: str | None = None
    causation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the event into a serializable dictionary.

        Returns:
            A dictionary representation of the event.
        """
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "schema_version": self.schema_version,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
        }

    @property
    def name(self) -> str:
        """Return the canonical event name.

        Returns:
            The event type.
        """
        return self.event_type

    def __str__(self) -> str:
        """Return a human-readable event representation."""
        return (
            f"{self.__class__.__name__}("
            f"event_type='{self.event_type}', "
            f"event_id='{self.event_id}')"
        )
