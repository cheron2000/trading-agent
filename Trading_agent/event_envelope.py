"""
communication.models.event_envelope
==================================

Defines the immutable EventEnvelope used by the Communication Layer.

An EventEnvelope wraps a Foundation BaseEvent with communication-specific
metadata required for routing and transport while remaining completely
transport agnostic.

The envelope intentionally avoids duplicating fields already defined by
BaseEvent (such as event_id, correlation_id, causation_id, or timestamp).

Python Version:
    3.13+
"""

from __future__ import annotations

from dataclasses import dataclass

from foundation.events.base_event import BaseEvent

from .event_metadata import EventMetadata
from .event_priority import EventPriority


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """Immutable communication envelope.

    An EventEnvelope is the canonical container exchanged within the
    Communication Layer. It combines a Foundation event with
    communication metadata while remaining independent of any transport
    implementation.

    Attributes:
        event:
            Immutable Foundation event instance.

        metadata:
            Communication metadata associated with the event.

        priority:
            Dispatch priority used by the EventBus. This value is kept
            separate for efficient scheduling and must remain consistent
            with ``metadata.priority``.
    """

    event: BaseEvent
    metadata: EventMetadata
    priority: EventPriority

    def __post_init__(self) -> None:
        """Validate the envelope.

        Raises:
            ValueError:
                If the priority stored in the envelope differs from the
                priority contained in the metadata.
        """
        if self.priority != self.metadata.priority:
            raise ValueError(
                "Envelope priority must match "
                "EventMetadata.priority."
            )

    @property
    def source_component(self) -> str:
        """Return the originating component.

        Returns:
            The source component name from the metadata.
        """
        return self.metadata.source_component

    @property
    def target_component(self) -> str | None:
        """Return the destination component.

        Returns:
            The target component name or ``None`` for broadcast events.
        """
        return self.metadata.target_component

    @property
    def retry_count(self) -> int:
        """Return the current retry count.

        Returns:
            Number of delivery attempts already performed.
        """
        return self.metadata.retry_count

    @property
    def transport_id(self) -> str | None:
        """Return the optional transport identifier.

        Returns:
            The opaque transport identifier, if one exists.
        """
        return self.metadata.transport_id

    @property
    def created_at(self):
        """Return the metadata creation timestamp.

        Returns:
            UTC datetime from the metadata.
        """
        return self.metadata.created_at

    def to_dict(self) -> dict[str, object]:
        """Serialize the envelope deterministically.

        Notes:
            Serialization of the wrapped ``BaseEvent`` is delegated to
            the Foundation implementation.

        Returns:
            A deterministic dictionary representation suitable for
            downstream serializers.
        """
        return {
            "event": self.event,
            "metadata": self.metadata.to_dict(),
            "priority": self.priority.value,
        }

    def __str__(self) -> str:
        """Return a concise human-readable representation."""
        return (
            "EventEnvelope("
            f"event={self.event.__class__.__name__}, "
            f"source='{self.source_component}', "
            f"priority='{self.priority.value}')"
        )