"""
Unit tests for communication.models.event_priority.

These tests verify the immutable EventPriority enumeration,
its public API, ordering semantics, and serialization behavior.
"""

from __future__ import annotations

import pytest

from communication.models import EventPriority


class TestEventPriority:
    """Test suite for EventPriority."""

    def test_enum_values_are_stable(self) -> None:
        """Verify the numeric values of every priority."""
        assert EventPriority.CRITICAL.value == 0
        assert EventPriority.HIGH.value == 1
        assert EventPriority.NORMAL.value == 2
        assert EventPriority.LOW.value == 3
        assert EventPriority.BACKGROUND.value == 4

    def test_default_returns_normal(self) -> None:
        """The default priority should always be NORMAL."""
        assert EventPriority.default() == EventPriority.NORMAL

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0, EventPriority.CRITICAL),
            (1, EventPriority.HIGH),
            (2, EventPriority.NORMAL),
            (3, EventPriority.LOW),
            (4, EventPriority.BACKGROUND),
        ],
    )
    def test_from_value(
        self,
        value: int,
        expected: EventPriority,
    ) -> None:
        """Verify conversion from integer values."""
        assert EventPriority.from_value(value) == expected

    @pytest.mark.parametrize(
        "value",
        [-1, 5, 100, 999],
    )
    def test_from_value_invalid(self, value: int) -> None:
        """Invalid values should raise ValueError."""
        with pytest.raises(ValueError):
            EventPriority.from_value(value)

    @pytest.mark.parametrize(
        ("priority", "expected"),
        [
            (EventPriority.CRITICAL, 0),
            (EventPriority.HIGH, 1),
            (EventPriority.NORMAL, 2),
            (EventPriority.LOW, 3),
            (EventPriority.BACKGROUND, 4),
        ],
    )
    def test_level_property(
        self,
        priority: EventPriority,
        expected: int,
    ) -> None:
        """Verify the numeric level property."""
        assert priority.level == expected

    @pytest.mark.parametrize(
        ("priority", "expected"),
        [
            (EventPriority.CRITICAL, True),
            (EventPriority.HIGH, True),
            (EventPriority.NORMAL, False),
            (EventPriority.LOW, False),
            (EventPriority.BACKGROUND, False),
        ],
    )
    def test_is_urgent_property(
        self,
        priority: EventPriority,
        expected: bool,
    ) -> None:
        """Verify urgent classification."""
        assert priority.is_urgent == expected

    @pytest.mark.parametrize(
        ("priority", "expected"),
        [
            (EventPriority.CRITICAL, "critical"),
            (EventPriority.HIGH, "high"),
            (EventPriority.NORMAL, "normal"),
            (EventPriority.LOW, "low"),
            (EventPriority.BACKGROUND, "background"),
        ],
    )
    def test_string_representation(
        self,
        priority: EventPriority,
        expected: str,
    ) -> None:
        """Verify deterministic string serialization."""
        assert str(priority) == expected

    def test_enum_ordering(self) -> None:
        """Verify ordering semantics."""
        assert EventPriority.CRITICAL < EventPriority.HIGH
        assert EventPriority.HIGH < EventPriority.NORMAL
        assert EventPriority.NORMAL < EventPriority.LOW
        assert EventPriority.LOW < EventPriority.BACKGROUND

    def test_hashability(self) -> None:
        """EventPriority members should be hashable."""
        priorities = {
            EventPriority.CRITICAL,
            EventPriority.NORMAL,
            EventPriority.NORMAL,
        }

        assert len(priorities) == 2

    def test_equality(self) -> None:
        """Verify equality semantics."""
        assert EventPriority.NORMAL == EventPriority.NORMAL
        assert EventPriority.NORMAL != EventPriority.HIGH

    def test_membership(self) -> None:
        """Every priority should exist in the enumeration."""
        assert EventPriority.CRITICAL in EventPriority
        assert EventPriority.HIGH in EventPriority
        assert EventPriority.NORMAL in EventPriority
        assert EventPriority.LOW in EventPriority
        assert EventPriority.BACKGROUND in EventPriority
        