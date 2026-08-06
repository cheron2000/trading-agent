"""
Immutable metadata attached to communication events.

This model is transport-agnostic and contains only routing and
communication-layer metadata. It must NOT duplicate BaseEvent
identity or timestamp fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar

from .event_priority import EventPriority


@dataclass(frozen=True, slots=True)
class EventMetadata:
    """
    Immutable communication metadata for event routing and tracing.

    Attributes:
        source_component:
            Name of the component that produced the event.

        target_component:
            Optional destination component.

        priority:
            Event priority level used for scheduling and routing.

        retry_count:
            Number of retry attempts performed for this event.

        transport_id:
            Optional identifier assigned by transport layer.

        created_at:
            Timestamp when metadata was created (UTC, ISO-8601 source).
    """

    source_component: str
    priority: EventPriority = EventPriority.NORMAL
    retry_count: int = 0
    target_component: str | None = None
    transport_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # -----------------------------
    # Validation constants
    # -----------------------------

    _MAX_COMPONENT_LENGTH: ClassVar[int] = 255
    _MAX_TRANSPORT_ID_LENGTH: ClassVar[int] = 255
    _MAX_RETRY_COUNT: ClassVar[int] = 10_000

    def __post_init__(self) -> None:
        """Validate immutable metadata."""
        self._validate_source_component()
        self._validate_target_component()
        self._validate_transport_id()
        self._validate_retry_count()

    def _validate_source_component(self) -> None:
        value = self.source_component.strip()

        if not value:
            raise ValueError("source_component must not be empty.")

        if len(value) > self._MAX_COMPONENT_LENGTH:
            raise ValueError("source_component exceeds max length.")

    def _validate_target_component(self) -> None:
        if self.target_component is None:
            return

        value = self.target_component.strip()

        if not value:
            raise ValueError("target_component cannot be empty string.")

        if len(value) > self._MAX_COMPONENT_LENGTH:
            raise ValueError("target_component exceeds max length.")

    def _validate_transport_id(self) -> None:
        if self.transport_id is None:
            return

        value = self.transport_id.strip()

        if not value:
            raise ValueError("transport_id cannot be empty string.")

        if len(value) > self._MAX_TRANSPORT_ID_LENGTH:
            raise ValueError("transport_id exceeds max length.")

    def _validate_retry_count(self) -> None:
        if self.retry_count < 0:
            raise ValueError("retry_count cannot be negative.")

        if self.retry_count > self._MAX_RETRY_COUNT:
            raise ValueError("retry_count exceeds allowed limit.")

    # -----------------------------
    # Normalization helpers
    # -----------------------------

    def _normalize_component(self, value: str) -> str:
        """Normalize component names (deterministic formatting)."""
        return value.strip()

    def _normalize_optional(self, value: str | None) -> str | None:
        """Normalize optional string fields."""
        if value is None:
            return None
        return value.strip() or None

    # -----------------------------
    # Properties
    # -----------------------------

    @property
    def is_retry_event(self) -> bool:
        """Return True if this event has retries."""
        return self.retry_count > 0

    @property
    def is_routing_targeted(self) -> bool:
        """Return True if event has a specific target component."""
        return self.target_component is not None

    @property
    def is_transport_assigned(self) -> bool:
        """Return True if transport layer assigned an ID."""
        return self.transport_id is not None

    # -----------------------------
    # Serialization
    # -----------------------------

    def to_dict(self) -> dict[str, object]:
        """
        Deterministically serialize metadata.

        Returns:
            Dictionary representation with stable ordering guarantees.
        """
        created_at_iso = self.created_at
        if created_at_iso.tzinfo is None:
            created_at_iso = created_at_iso.replace(tzinfo=timezone.utc)

        return {
            "source_component": self.source_component,
            "target_component": self.target_component,
            "priority": self.priority.value,
            "retry_count": self.retry_count,
            "transport_id": self.transport_id,
            "created_at": created_at_iso.isoformat(),
        }

    def __str__(self) -> str:
        """Return human-readable representation."""
        return (
            "EventMetadata("
            f"source='{self.source_component}', "
            f"target='{self.target_component}', "
            f"priority={self.priority}, "
            f"retries={self.retry_count})"
        )

    # -----------------------------
    # Dataclass behavior guarantees
    # -----------------------------

    def __eq__(self, other: object) -> bool:
        """
        Equality is strictly structural and deterministic.

        Only public fields are considered.
        """
        if not isinstance(other, EventMetadata):
            return False

        return (
            self.source_component == other.source_component
            and self.target_component == other.target_component
            and self.priority == other.priority
            and self.retry_count == other.retry_count
            and self.transport_id == other.transport_id
            and self.created_at == other.created_at
        )

    def __hash__(self) -> int:
        """
        Hash is derived from immutable public state only.

        Required because frozen dataclass hashing may include
        default behavior that we explicitly control for stability.
        """
        return hash(
            (
                self.source_component,
                self.target_component,
                self.priority,
                self.retry_count,
                self.transport_id,
                self.created_at,
            )
        )

    # -----------------------------
    # Safety / invariants
    # -----------------------------

    def _finalize(self) -> None:
        """
        Internal no-op safeguard hook.

        Exists to preserve future compatibility for:
        - instrumentation
        - tracing
        - debugging extensions

        Must NOT mutate state.
        """
        return None
