"""
communication.models.heartbeat
==============================

Defines the immutable heartbeat model used by the Communication Layer.

A Heartbeat represents the current operational state of a component.
It is intended for health monitoring, observability, and diagnostics.

This model contains no runtime behavior beyond validation and is
transport-independent.

Python Version:
    3.13+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from .health_state import HealthState


@dataclass(frozen=True, slots=True)
class Heartbeat:
    """Immutable heartbeat snapshot.

    Attributes:
        component_name:
            Unique name of the reporting component.

        health_state:
            Current operational health state.

        last_seen:
            UTC timestamp indicating when the heartbeat was generated.

        uptime_seconds:
            Number of seconds the component has been continuously running.

        version:
            Semantic version of the reporting component.
    """

    component_name: str
    health_state: HealthState
    last_seen: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )
    uptime_seconds: float = 0.0
    version: str = "1.0.0"

    _MAX_COMPONENT_LENGTH: Final[int] = 255
    _MAX_VERSION_LENGTH: Final[int] = 32

    def __post_init__(self) -> None:
        """Validate heartbeat fields.

        Raises:
            ValueError:
                If one or more fields contain invalid values.
        """
        if not self.component_name.strip():
            raise ValueError(
                "component_name must not be empty."
            )

        if len(self.component_name) > self._MAX_COMPONENT_LENGTH:
            raise ValueError(
                "component_name exceeds maximum length."
            )

        if self.last_seen.tzinfo is None:
            raise ValueError(
                "last_seen must be timezone-aware."
            )

        if self.uptime_seconds < 0:
            raise ValueError(
                "uptime_seconds cannot be negative."
            )

        if not self.version.strip():
            raise ValueError(
                "version must not be empty."
            )

        if len(self.version) > self._MAX_VERSION_LENGTH:
            raise ValueError(
                "version exceeds maximum length."
            )

    @property
    def is_healthy(self) -> bool:
        """Return whether the component is operational.

        Returns:
            True if the health state represents an operational component.
        """
        return self.health_state.is_operational

    def to_dict(self) -> dict[str, str | float]:
        """Serialize the heartbeat deterministically.

        Returns:
            Dictionary suitable for JSON serialization.

        Notes:
            - Enum values are serialized by value.
            - Datetimes use ISO-8601 UTC format.
            - Keys are emitted in stable order.
        """
        return {
            "component_name": self.component_name,
            "health_state": self.health_state.value,
            "last_seen": self.last_seen.isoformat(),
            "uptime_seconds": self.uptime_seconds,
            "version": self.version,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
    ) -> "Heartbeat":
        """Construct a Heartbeat from serialized data.

        Args:
            data:
                Serialized heartbeat dictionary.

        Returns:
            Immutable Heartbeat instance.

        Raises:
            KeyError:
                If required fields are missing.

            ValueError:
                If field values are invalid.
        """
        return cls(
            component_name=str(data["component_name"]),
            health_state=HealthState.from_value(
                str(data["health_state"])
            ),
            last_seen=datetime.fromisoformat(
                str(data["last_seen"])
            ),
            uptime_seconds=float(data["uptime_seconds"]),
            version=str(data["version"]),
        )

    def __str__(self) -> str:
        """Return a concise human-readable representation."""
        return (
            "Heartbeat("
            f"component='{self.component_name}', "
            f"state='{self.health_state}', "
            f"uptime={self.uptime_seconds:.2f}s, "
            f"version='{self.version}')"
        )