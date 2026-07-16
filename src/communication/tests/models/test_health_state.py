"""
Unit tests for communication.models.health_state.

These tests verify the public API, lifecycle semantics, serialization,
and deterministic behavior of the HealthState enumeration.
"""

from __future__ import annotations

import pytest

from communication.models import HealthState


class TestHealthState:
    """Test suite for HealthState."""

    def test_enum_values_are_stable(self) -> None:
        """Verify serialized enum values remain stable."""
        assert HealthState.STARTING.value == "starting"
        assert HealthState.RUNNING.value == "running"
        assert HealthState.DEGRADED.value == "degraded"
        assert HealthState.STOPPING.value == "stopping"
        assert HealthState.STOPPED.value == "stopped"
        assert HealthState.FAILED.value == "failed"

    def test_default_returns_starting(self) -> None:
        """Verify the default lifecycle state."""
        assert HealthState.default() == HealthState.STARTING

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("starting", HealthState.STARTING),
            ("running", HealthState.RUNNING),
            ("degraded", HealthState.DEGRADED),
            ("stopping", HealthState.STOPPING),
            ("stopped", HealthState.STOPPED),
            ("failed", HealthState.FAILED),
        ],
    )
    def test_from_value(
        self,
        value: str,
        expected: HealthState,
    ) -> None:
        """Verify conversion from serialized values."""
        assert HealthState.from_value(value) is expected

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "RUNNING",
            "Running",
            "healthy",
            "offline",
            "error",
            "unknown",
        ],
    )
    def test_from_value_invalid(self, value: str) -> None:
        """Invalid values should raise ValueError."""
        with pytest.raises(ValueError):
            HealthState.from_value(value)

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            (HealthState.STARTING, False),
            (HealthState.RUNNING, True),
            (HealthState.DEGRADED, True),
            (HealthState.STOPPING, False),
            (HealthState.STOPPED, False),
            (HealthState.FAILED, False),
        ],
    )
    def test_is_operational(
        self,
        state: HealthState,
        expected: bool,
    ) -> None:
        """Verify operational state classification."""
        assert state.is_operational is expected

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            (HealthState.STARTING, False),
            (HealthState.RUNNING, False),
            (HealthState.DEGRADED, False),
            (HealthState.STOPPING, False),
            (HealthState.STOPPED, True),
            (HealthState.FAILED, True),
        ],
    )
    def test_is_terminal(
        self,
        state: HealthState,
        expected: bool,
    ) -> None:
        """Verify terminal lifecycle classification."""
        assert state.is_terminal is expected

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            (HealthState.STARTING, "starting"),
            (HealthState.RUNNING, "running"),
            (HealthState.DEGRADED, "degraded"),
            (HealthState.STOPPING, "stopping"),
            (HealthState.STOPPED, "stopped"),
            (HealthState.FAILED, "failed"),
        ],
    )
    def test_string_representation(
        self,
        state: HealthState,
        expected: str,
    ) -> None:
        """Verify deterministic string serialization."""
        assert str(state) == expected

    def test_hashability(self) -> None:
        """HealthState members should be hashable."""
        states = {
            HealthState.RUNNING,
            HealthState.RUNNING,
            HealthState.FAILED,
        }

        assert len(states) == 2

    def test_equality(self) -> None:
        """Verify equality semantics."""
        assert HealthState.RUNNING == HealthState.RUNNING
        assert HealthState.RUNNING != HealthState.DEGRADED

    def test_membership(self) -> None:
        """Every lifecycle state should exist in the enumeration."""
        assert HealthState.STARTING in HealthState
        assert HealthState.RUNNING in HealthState
        assert HealthState.DEGRADED in HealthState
        assert HealthState.STOPPING in HealthState
        assert HealthState.STOPPED in HealthState
        assert HealthState.FAILED in HealthState

    def test_enum_member_count(self) -> None:
        """The enumeration should contain exactly six members."""
        assert len(HealthState) == 6