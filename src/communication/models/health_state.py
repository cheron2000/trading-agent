"""
communication.models.health_state
================================

Defines the canonical health lifecycle used by the Communication Layer.

This module provides a transport-independent health state enumeration
used by heartbeat messages, monitoring, and operational health reporting.

If the Foundation Layer exposes an equivalent HealthState or lifecycle
enumeration, this module should re-export that type instead of defining
a duplicate. This implementation serves as the canonical Communication
Layer contract until integrated with the frozen Foundation.

Python Version:
    3.13+

Author:
    AI Trading Operating System
"""

from __future__ import annotations

from enum import StrEnum


class HealthState(StrEnum):
    """Represents the operational health state of a system component.

    The lifecycle values are part of the frozen public API and must
    remain stable across compatible versions.

    Values:
        STARTING:
            Component is initializing.

        RUNNING:
            Component is operating normally.

        DEGRADED:
            Component is operational but experiencing reduced capability.

        STOPPING:
            Component is shutting down gracefully.

        STOPPED:
            Component has stopped normally.

        FAILED:
            Component encountered a fatal error and is no longer
            operational.
    """

    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"

    @property
    def is_operational(self) -> bool:
        """Return whether the component is considered operational.

        Returns:
            True when the component can continue serving requests,
            otherwise False.
        """
        return self in (
            HealthState.RUNNING,
            HealthState.DEGRADED,
        )

    @property
    def is_terminal(self) -> bool:
        """Return whether the state is terminal.

        Returns:
            True if the component has reached a terminal lifecycle state.
        """
        return self in (
            HealthState.STOPPED,
            HealthState.FAILED,
        )

    @classmethod
    def default(cls) -> "HealthState":
        """Return the default initial health state.

        Returns:
            HealthState.STARTING.
        """
        return cls.STARTING

    @classmethod
    def from_value(cls, value: str) -> "HealthState":
        """Create a HealthState from its serialized value.

        Args:
            value:
                Serialized lowercase health state.

        Returns:
            Corresponding HealthState instance.

        Raises:
            ValueError:
                If the supplied value is not a valid health state.
        """
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(
                f"Unsupported health state: {value}"
            ) from exc

    def __str__(self) -> str:
        """Return the canonical serialized representation.

        Returns:
            Lowercase string representation of the health state.
        """
        return self.value