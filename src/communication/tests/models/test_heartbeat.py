"""
Unit tests for communication.models.heartbeat.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from communication.models import Heartbeat
from communication.models.health_state import HealthState


class TestHeartbeat:

    def test_valid_creation(self) -> None:
        h = Heartbeat(
            component_name="orion",
            health_state=HealthState.RUNNING,
            uptime_seconds=3600,
            version="1.0.0",
        )
        assert h.component_name == "orion"
        assert h.health_state == HealthState.RUNNING
        assert h.uptime_seconds == 3600
        assert h.version == "1.0.0"

    def test_last_seen_default_is_utc(self) -> None:
        h = Heartbeat(
            component_name="x",
            health_state=HealthState.RUNNING,
            uptime_seconds=0,
            version="1.0",
        )
        assert h.last_seen.tzinfo is not None

    def test_last_seen_per_instance(self) -> None:
        h1 = Heartbeat(
            component_name="x",
            health_state=HealthState.RUNNING,
            uptime_seconds=0,
            version="1.0",
        )
        h2 = Heartbeat(
            component_name="x",
            health_state=HealthState.RUNNING,
            uptime_seconds=0,
            version="1.0",
        )
        assert h1.last_seen <= h2.last_seen

    def test_empty_component_name_raises(self) -> None:
        with pytest.raises(ValueError):
            Heartbeat(
                component_name="",
                health_state=HealthState.RUNNING,
                uptime_seconds=0,
                version="1.0",
            )

    def test_whitespace_component_name_raises(self) -> None:
        with pytest.raises(ValueError):
            Heartbeat(
                component_name="  ",
                health_state=HealthState.RUNNING,
                uptime_seconds=0,
                version="1.0",
            )

    def test_component_name_too_long_raises(self) -> None:
        with pytest.raises(ValueError):
            Heartbeat(
                component_name="a" * 256,
                health_state=HealthState.RUNNING,
                uptime_seconds=0,
                version="1.0",
            )

    def test_empty_version_raises(self) -> None:
        with pytest.raises(ValueError):
            Heartbeat(
                component_name="x",
                health_state=HealthState.RUNNING,
                uptime_seconds=0,
                version="",
            )

    def test_version_too_long_raises(self) -> None:
        with pytest.raises(ValueError):
            Heartbeat(
                component_name="x",
                health_state=HealthState.RUNNING,
                uptime_seconds=0,
                version="a" * 33,
            )

    def test_negative_uptime_raises(self) -> None:
        with pytest.raises(ValueError):
            Heartbeat(
                component_name="x",
                health_state=HealthState.RUNNING,
                uptime_seconds=-1,
                version="1.0",
            )

    def test_uptime_exceeds_limit_raises(self) -> None:
        with pytest.raises(ValueError):
            Heartbeat(
                component_name="x",
                health_state=HealthState.RUNNING,
                uptime_seconds=10**12 + 1,
                version="1.0",
            )

    def test_is_healthy_running(self) -> None:
        h = Heartbeat(
            component_name="x",
            health_state=HealthState.RUNNING,
            uptime_seconds=0,
            version="1.0",
        )
        assert h.is_healthy is True

    def test_is_healthy_degraded(self) -> None:
        h = Heartbeat(
            component_name="x",
            health_state=HealthState.DEGRADED,
            uptime_seconds=0,
            version="1.0",
        )
        assert h.is_healthy is True

    def test_is_healthy_failed(self) -> None:
        h = Heartbeat(
            component_name="x",
            health_state=HealthState.FAILED,
            uptime_seconds=0,
            version="1.0",
        )
        assert h.is_healthy is False

    def test_is_terminal_stopped(self) -> None:
        h = Heartbeat(
            component_name="x",
            health_state=HealthState.STOPPED,
            uptime_seconds=0,
            version="1.0",
        )
        assert h.is_terminal is True

    def test_is_terminal_running(self) -> None:
        h = Heartbeat(
            component_name="x",
            health_state=HealthState.RUNNING,
            uptime_seconds=0,
            version="1.0",
        )
        assert h.is_terminal is False

    def test_uptime_hours(self) -> None:
        h = Heartbeat(
            component_name="x",
            health_state=HealthState.RUNNING,
            uptime_seconds=7200,
            version="1.0",
        )
        assert h.uptime_hours == 2.0

    def test_immutability(self) -> None:
        h = Heartbeat(
            component_name="x",
            health_state=HealthState.RUNNING,
            uptime_seconds=0,
            version="1.0",
        )
        with pytest.raises((AttributeError, TypeError)):
            h.component_name = "y"  # type: ignore[misc]

    def test_equality(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        h1 = Heartbeat(
            component_name="x",
            health_state=HealthState.RUNNING,
            uptime_seconds=10,
            version="1.0",
            last_seen=ts,
        )
        h2 = Heartbeat(
            component_name="x",
            health_state=HealthState.RUNNING,
            uptime_seconds=10,
            version="1.0",
            last_seen=ts,
        )
        assert h1 == h2

    def test_hashable(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        h = Heartbeat(
            component_name="x",
            health_state=HealthState.RUNNING,
            uptime_seconds=0,
            version="1.0",
            last_seen=ts,
        )
        assert isinstance(hash(h), int)

    def test_to_dict(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        h = Heartbeat(
            component_name="orion",
            health_state=HealthState.RUNNING,
            uptime_seconds=100,
            version="2.0",
            last_seen=ts,
        )
        d = h.to_dict()
        assert d["component_name"] == "orion"
        assert d["health_state"] == "running"
        assert d["uptime_seconds"] == 100
        assert d["version"] == "2.0"

    def test_str_representation(self) -> None:
        h = Heartbeat(
            component_name="orion",
            health_state=HealthState.RUNNING,
            uptime_seconds=0,
            version="1.0",
        )
        assert "orion" in str(h)
        assert "running" in str(h)
