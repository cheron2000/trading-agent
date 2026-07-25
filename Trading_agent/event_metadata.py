"""
communication.models.event_metadata
===================================

Defines the immutable communication metadata associated with an event.

This model contains only communication-layer metadata and intentionally
does not duplicate identifiers or timestamps that belong to BaseEvent.

The metadata is transport-agnostic and safe to serialize.

Python Version:
    3.13+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from .event_priority import EventPriority


@dataclass(frozen=True, slots=True)
class EventMetadata:
    """Immutable communication metadata.

    This object accompanies a BaseEvent inside an EventEnvelope and
    contains metadata required by the communication infrastructure.

    Attributes:
        source_component:
            Name of the component that published the event.

        target_component:
            Optional destination component. ``None`` indicates broadcast.

        priority:
            Communication priority assigned to the event.

        retry_count:
            Number of delivery retry attempts already performed.

        transport_id:
            Optional transport-specific identifier assigned by a future
            transport adapter. This field is opaque to the communication
            models.

        created_at:
            UTC timestamp indicating when this metadata instance was
            created.
    """

    source_component: str
    target_component: str | None = None
    priority: EventPriority = EventPriority.NORMAL
    retry_count: int = 0
    transport_id: str | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    _MAX_COMPONENT_LENGTH: Final[int] = 255
    _MAX_TRANSPORT_ID_LENGTH: Final[int] = 255

    def __post_init__(self) -> None:
        """Validate the metadata.

        Raises:
            ValueError:
                If one or more fields contain invalid values.
        """
        self._validate_component(
            "source_component",
            self.source_component,
        )

        if self.target_component is not None:
            self._validate_component(
                "target_component",
                self.target_component,
            )

        if self.retry_count < 0:
            raise ValueError(
                "retry_count cannot be negative."
            )

        if self.transport_id is not None:
            if not self.transport_id.strip():
                raise ValueError(
                    "transport_id cannot be empty."
                )

            if (
                len(self.transport_id)
                > self._MAX_TRANSPORT_ID_LENGTH
            ):
                raise ValueError(
                    "transport_id exceeds maximum length."
                )

        if self.created_at.tzinfo is None:
            raise ValueError(
                "created_at must be timezone-aware."
            )

    @classmethod
    def _validate_component(
        cls,
        field_name: str,
        value: str,
    ) -> None:
        """Validate a component name.

        Args:
            field_name:
                Name of the field being validated.

            value:
                Component identifier.

        Raises:
            ValueError:
                If the component name is invalid.
        """
        if not value.strip():
            raise ValueError(
                f"{field_name} must not be empty."
            )

        if len(value) > cls._MAX_COMPONENT_LENGTH:
            raise ValueError(
                f"{field_name} exceeds maximum length."
            )

    def to_dict(self) -> dict[str, str | int | None]:
        """Serialize metadata into a deterministic dictionary.

        Returns:
            Dictionary suitable for JSON serialization.

        Notes:
            - Enum values are serialized by value.
            - Timestamps use ISO-8601 UTC format.
            - Keys are emitted in stable order.
        """
        return {
            "source_component": self.source_component,
            "target_component": self.target_component,
            "priority": self.priority.value,
            "retry_count": self.retry_count,
            "transport_id": self.transport_id,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
    ) -> "EventMetadata":
        """Construct metadata from serialized data.

        Args:
            data:
                Serialized metadata dictionary.

        Returns:
            Immutable EventMetadata instance.

        Raises:
            KeyError:
                If a required field is missing.

            ValueError:
                If serialized values are invalid.
        """
        return cls(
            source_component=str(data["source_component"]),
            target_component=(
                None
                if data["target_component"] is None
                else str(data["target_component"])
            ),
            priority=EventPriority.from_value(
                int(data["priority"])
            ),
            retry_count=int(data["retry_count"]),
            transport_id=(
                None
                if data["transport_id"] is None
                else str(data["transport_id"])
            ),
            created_at=datetime.fromisoformat(
                str(data["created_at"])
            ),
        )

    @property
    def is_broadcast(self) -> bool:
        """Return whether the event targets all subscribers.

        Returns:
            True when no specific target component is defined.
        """
        return self.target_component is None

    def __str__(self) -> str:
        """Return a concise human-readable representation."""
        target = self.target_component or "*"

        return (
            "EventMetadata("
            f"source='{self.source_component}', "
            f"target='{target}', "
            f"priority='{self.priority}', "
            f"retries={self.retry_count})"
        )