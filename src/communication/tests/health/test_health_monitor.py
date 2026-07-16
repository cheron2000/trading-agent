"""
Unit tests for communication.health.health_monitor.HealthMonitor.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta
from typing import Callable
from unittest.mock import MagicMock

import pytest

from foundation.base_event import BaseEvent
from communication.health import HealthMonitor
from communication.interfaces import IHealthMonitor
from communication.models.heartbeat import Heartbeat
from communication.models.health_state import HealthState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_heartbeat(
    component: str = "orion",
    state: HealthState = HealthState.RUNNING,
    uptime: int = 100,
    version: str = "1.0.0",
    last_seen: datetime | None = None,
) -> Heartbeat:
    kwargs = dict(
        component_name=component,
        health_state=state,
        uptime_seconds=uptime,
        version=version,
    )
    if last_seen is not None:
        kwargs["last_seen"] = last_seen
    return Heartbeat(**kwargs)


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

class TestHealthMonitorProtocolCompliance:

    def test_satisfies_ihealthmonitor_protocol(self) -> None:
        assert isinstance(HealthMonitor(), IHealthMonitor)


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

class TestHealthMonitorInit:

    def test_default_liveness_window(self) -> None:
        m = HealthMonitor()
        assert m._liveness_window == 30

    def test_custom_liveness_window(self) -> None:
        m = HealthMonitor(liveness_window_seconds=60)
        assert m._liveness_window == 60

    def test_zero_liveness_window_raises(self) -> None:
        with pytest.raises(ValueError):
            HealthMonitor(liveness_window_seconds=0)

    def test_negative_liveness_window_raises(self) -> None:
        with pytest.raises(ValueError):
            HealthMonitor(liveness_window_seconds=-5)


# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------

class TestHealthMonitorRegister:

    def test_register_adds_component(self) -> None:
        m = HealthMonitor()
        m.register("orion")
        assert "orion" in m.registered_components

    def test_register_empty_name_raises(self) -> None:
        m = HealthMonitor()
        with pytest.raises(ValueError):
            m.register("")

    def test_register_whitespace_name_raises(self) -> None:
        m = HealthMonitor()
        with pytest.raises(ValueError):
            m.register("   ")

    def test_register_duplicate_is_noop(self) -> None:
        m = HealthMonitor()
        m.register("orion")
        m.register("orion")  # must not raise
        assert len(m.registered_components) == 1

    def test_register_multiple_components(self) -> None:
        m = HealthMonitor()
        m.register("orion")
        m.register("athena")
        assert m.registered_components == frozenset({"orion", "athena"})


# ---------------------------------------------------------------------------
# record_heartbeat()
# ---------------------------------------------------------------------------

class TestHealthMonitorRecordHeartbeat:

    def test_record_heartbeat_stores_latest(self) -> None:
        m = HealthMonitor()
        hb = make_heartbeat("orion")
        m.record_heartbeat(hb)
        assert m.get_heartbeat("orion") is hb

    def test_record_heartbeat_none_raises(self) -> None:
        m = HealthMonitor()
        with pytest.raises(ValueError):
            m.record_heartbeat(None)  # type: ignore

    def test_record_heartbeat_auto_registers(self) -> None:
        m = HealthMonitor()
        m.record_heartbeat(make_heartbeat("orion"))
        assert "orion" in m.registered_components

    def test_record_heartbeat_updates_latest(self) -> None:
        m = HealthMonitor()
        hb1 = make_heartbeat("orion", uptime=10)
        hb2 = make_heartbeat("orion", uptime=20)
        m.record_heartbeat(hb1)
        m.record_heartbeat(hb2)
        assert m.get_heartbeat("orion").uptime_seconds == 20

    def test_record_heartbeat_publishes_event_on_bus(self) -> None:
        bus = MagicMock()
        m = HealthMonitor(event_bus=bus)
        m.record_heartbeat(make_heartbeat("orion"))
        bus.publish.assert_called_once()
        published_event: BaseEvent = bus.publish.call_args[0][0]
        assert published_event.event_type == "health.heartbeat.recorded"

    def test_record_heartbeat_no_bus_does_not_raise(self) -> None:
        m = HealthMonitor()
        m.record_heartbeat(make_heartbeat("orion"))  # must not raise


# ---------------------------------------------------------------------------
# is_alive()
# ---------------------------------------------------------------------------

class TestHealthMonitorIsAlive:

    def test_alive_running_component(self) -> None:
        m = HealthMonitor(liveness_window_seconds=30)
        m.record_heartbeat(make_heartbeat("orion", state=HealthState.RUNNING))
        assert m.is_alive("orion") is True

    def test_alive_degraded_component(self) -> None:
        m = HealthMonitor(liveness_window_seconds=30)
        m.record_heartbeat(make_heartbeat("orion", state=HealthState.DEGRADED))
        assert m.is_alive("orion") is True

    def test_not_alive_stopped_component(self) -> None:
        m = HealthMonitor(liveness_window_seconds=30)
        m.record_heartbeat(make_heartbeat("orion", state=HealthState.STOPPED))
        assert m.is_alive("orion") is False

    def test_not_alive_failed_component(self) -> None:
        m = HealthMonitor(liveness_window_seconds=30)
        m.record_heartbeat(make_heartbeat("orion", state=HealthState.FAILED))
        assert m.is_alive("orion") is False

    def test_not_alive_unknown_component(self) -> None:
        m = HealthMonitor()
        assert m.is_alive("ghost") is False

    def test_not_alive_registered_but_no_heartbeat(self) -> None:
        m = HealthMonitor()
        m.register("orion")
        assert m.is_alive("orion") is False

    def test_not_alive_expired_heartbeat(self) -> None:
        m = HealthMonitor(liveness_window_seconds=1)
        old_ts = datetime.now(timezone.utc) - timedelta(seconds=60)
        m.record_heartbeat(make_heartbeat("orion", state=HealthState.RUNNING, last_seen=old_ts))
        assert m.is_alive("orion") is False

    def test_alive_within_liveness_window(self) -> None:
        m = HealthMonitor(liveness_window_seconds=30)
        recent_ts = datetime.now(timezone.utc) - timedelta(seconds=5)
        m.record_heartbeat(make_heartbeat("orion", state=HealthState.RUNNING, last_seen=recent_ts))
        assert m.is_alive("orion") is True

    def test_not_alive_starting_state(self) -> None:
        m = HealthMonitor(liveness_window_seconds=30)
        m.record_heartbeat(make_heartbeat("orion", state=HealthState.STARTING))
        assert m.is_alive("orion") is False

    def test_not_alive_stopping_state(self) -> None:
        m = HealthMonitor(liveness_window_seconds=30)
        m.record_heartbeat(make_heartbeat("orion", state=HealthState.STOPPING))
        assert m.is_alive("orion") is False
