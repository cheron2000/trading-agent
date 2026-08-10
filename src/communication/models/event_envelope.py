"""
Immutable event envelope for the Communication Layer.

An EventEnvelope combines a Foundation BaseEvent with immutable
communication metadata. It is the canonical transport-independent
container exchanged between communication components.

The envelope does not implement routing, transport, scheduling,
serialization, or business logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from foundation.base_event import BaseEvent

from .event_metadata import EventMetadata
from .event_priority import EventPriority


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """Immutable wrapper around a BaseEvent.

    Attributes:
        event:
            Immutable Foundation event.

        metadata:
            Communication metadata associated with the event.

        priority:
            Dispatch priority for the communication layer.
    """

    event: BaseEvent
    metadata: EventMetadata
    priority: EventPriority

    def __post_init__(self) -> None:
        """Validate the envelope."""

        if self.event is None:
            raise ValueError("event must not be None.")

        if self.metadata is None:
            raise ValueError("metadata must not be None.")

        if not isinstance(self.priority, EventPriority):
            raise TypeError("priority must be an EventPriority.")

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def created_at(self) -> datetime:
        """
        Return the creation timestamp of the wrapped event.

        This property delegates directly to the Foundation BaseEvent.
        """
        return self.event.occurred_at

    @property
    def event_type(self) -> str:
        """
        Return the canonical event type.

        Delegates to the wrapped Foundation event.
        """
        return self.event.event_type

    @property
    def event_id(self) -> str:
        """
        Return the unique identifier of the wrapped event.
        """
        return self.event.event_id

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        """
        Serialize the envelope deterministically.

        The wrapped event is serialized by delegating to the
        Foundation BaseEvent serializer.

        Returns:
            Stable dictionary representation suitable for transport.
        """

        return {
            "event": self.event.to_dict(),
            "metadata": self.metadata.to_dict(),
            "priority": self.priority.value,
        }

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def source_component(self) -> str:
        """
        Return the originating component.

        Delegates to the immutable EventMetadata.
        """
        return self.metadata.source_component

    @property
    def target_component(self) -> str | None:
        """
        Return the target component if specified.
        """
        return self.metadata.target_component

    @property
    def retry_count(self) -> int:
        """
        Return the retry count associated with this envelope.
        """
        return self.metadata.retry_count

    @property
    def transport_id(self) -> str | None:
        """
        Return the optional transport identifier.

        This value is transport-agnostic and may be None.
        """
        return self.metadata.transport_id

    @property
    def is_retry(self) -> bool:
        """
        Return True when the enclosed event is being retried.
        """
        return self.retry_count > 0
