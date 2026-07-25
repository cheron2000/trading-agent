"""
communication.models.event_priority
==================================

Defines the canonical event priority levels used throughout the
Communication Layer.

The priority values are transport-independent and determine the
relative dispatch precedence of events. Lower numeric values indicate
higher priority.

This module is intentionally free of business logic and transport-
specific behavior.

Python Version:
    3.13+

Author:
    AI Trading Operating System

License:
    Project Internal
"""

from __future__ import annotations

from enum import IntEnum


class EventPriority(IntEnum):
    """Canonical event priority levels.

    These values define the relative importance of events published
    through the Communication Layer. Implementations of the EventBus
    may use these values when scheduling or dispatching events.

    The numeric ordering is part of the public API and must remain
    stable after release.

    Attributes:
        CRITICAL:
            Highest priority. Reserved for events that require immediate
            processing to preserve system integrity.

        HIGH:
            High-priority operational events.

        NORMAL:
            Default priority for standard system communication.

        LOW:
            Lower-priority events that are not time-sensitive.

        BACKGROUND:
            Lowest priority. Intended for maintenance, telemetry,
            housekeeping, and deferred processing.
    """

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4

    @property
    def level(self) -> int:
        """Return the integer priority level.

        Returns:
            The numeric priority value.

        Example:
            >>> EventPriority.HIGH.level
            1
        """
        return int(self)

    @property
    def is_urgent(self) -> bool:
        """Determine whether the priority is considered urgent.

        Returns:
            True if the priority is CRITICAL or HIGH,
            otherwise False.
        """
        return self in (
            EventPriority.CRITICAL,
            EventPriority.HIGH,
        )

    @classmethod
    def default(cls) -> "EventPriority":
        """Return the default event priority.

        Returns:
            EventPriority.NORMAL.
        """
        return cls.NORMAL

    @classmethod
    def from_value(cls, value: int) -> "EventPriority":
        """Create an EventPriority from its numeric value.

        Args:
            value:
                Integer priority value.

        Returns:
            Corresponding EventPriority instance.

        Raises:
            ValueError:
                If the supplied value is not a valid priority.
        """
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(
                f"Unsupported event priority: {value}"
            ) from exc

    def __str__(self) -> str:
        """Return the canonical lowercase name.

        Returns:
            Lowercase enum name.
        """
        return self.name.lower()