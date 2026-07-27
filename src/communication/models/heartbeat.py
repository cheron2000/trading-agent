"""
Heartbeat model for Communication Layer health monitoring.

This model represents a lightweight, immutable signal emitted by
components to indicate liveness and operational state.

It is intentionally minimal and contains no business logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar

from .health_state import HealthState


@dataclass(frozen=True, slots=True)
class Heartbeat:
    """
    Immutable heartbeat signal emitted by system components.

    Attributes:
        component_name:
            Name of the emitting component.

        health_state:
            Current operational state of the component.

        last_seen:
            Timestamp of last activity (UTC).

        uptime_seconds:
            Total uptime of the component in seconds.

        version:
            Semantic version of the emitting component.
    """

    component_name: str
    health_state: HealthState
    uptime_seconds: int
    version: str
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # -----------------------------
    # Validation constants
    # -----------------------------

    _MAX_COMPONENT_LENGTH: ClassVar[int] = 255
    _MAX_VERSION_LENGTH: ClassVar[int] = 32
    _MAX_UPTIME_SECONDS: ClassVar[int] = 10**12

    def __post_init__(self) -> None:
        """Validate heartbeat integrity."""
        self._validate_component_name()
        self._validate_version()
        self._validate_uptime()

    def _validate_component_name(self) -> None:
        value = self.component_name.strip()

        if not value:
            raise ValueError("component_name must not be empty.")

        if len(value) > self._MAX_COMPONENT_LENGTH:
            raise ValueError("component_name exceeds maximum length.")

    def _validate_version(self) -> None:
        value = self.version.strip()

        if not value:
            raise ValueError("version must not be empty.")

        if len(value) > self._MAX_VERSION_LENGTH:
            raise ValueError("version exceeds maximum length.")

    def _validate_uptime(self) -> None:
        if self.uptime_seconds < 0:
            raise ValueError("uptime_seconds cannot be negative.")

        if self.uptime_seconds > self._MAX_UPTIME_SECONDS:
            raise ValueError("uptime_seconds exceeds allowed limit.")

    # -----------------------------
    # Normalization helpers
    # -----------------------------

    def _normalize_component(self, value: str) -> str:
        """Normalize component name."""
        return value.strip()

    def _normalize_version(self, value: str) -> str:
        """Normalize version string."""
        return value.strip()

    # -----------------------------
    # Health evaluation
    # -----------------------------

    @property
    def is_healthy(self) -> bool:
        """
        Return True if component is operational.

        Healthy states:
            RUNNING
            DEGRADED
        """
        return self.health_state.is_operational

    @property
    def is_terminal(self) -> bool:
        """
        Return True if component is in terminal state.
        """
        return self.health_state.is_terminal

    @property
    def uptime_hours(self) -> float:
        """Convert uptime seconds into hours."""
        return self.uptime_seconds / 3600.0

    # -----------------------------
    # Serialization
    # -----------------------------

    def to_dict(self) -> dict[str, object]:
        """
        Deterministically serialize heartbeat.

        Returns:
            Stable dictionary representation for transport.
        """
        ts = self.last_seen
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        return {
            "component_name": self.component_name,
            "health_state": self.health_state.value,
            "uptime_seconds": self.uptime_seconds,
            "version": self.version,
            "last_seen": ts.isoformat(),
        }

    def __str__(self) -> str:
        """Human-readable representation."""
        return (
            "Heartbeat("
            f"component='{self.component_name}', "
            f"state='{self.health_state}', "
            f"uptime={self.uptime_seconds}s, "
            f"version='{self.version}')"
        )

    # -----------------------------
    # Equality & Hashing
    # -----------------------------

    def __eq__(self, other: object) -> bool:
        """
        Structural equality based on public immutable state only.
        """
        if not isinstance(other, Heartbeat):
            return False

        return (
            self.component_name == other.component_name
            and self.health_state == other.health_state
            and self.uptime_seconds == other.uptime_seconds
            and self.version == other.version
            and self.last_seen == other.last_seen
        )

    def __hash__(self) -> int:
        """
        Stable hash based on immutable public fields.

        Ensures safe usage in sets and as dictionary keys.
        """
        return hash(
            (
                self.component_name,
                self.health_state,
                self.uptime_seconds,
                self.version,
                self.last_seen,
            )
        )

    # -----------------------------
    # Safety / invariants
    # -----------------------------

    def _finalize(self) -> None:
        """
        Internal extension hook.

        Reserved for future instrumentation only.
        Must remain side-effect free.
        """
        return
