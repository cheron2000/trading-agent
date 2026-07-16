"""
Protocol compliance tests for communication.interfaces.

Verifies that stub concrete classes satisfy IEventBus, IScheduler,
and IHealthMonitor via isinstance() checks and structural matching.
"""

from __future__ import annotations

from typing import Callable

from foundation.base_event import BaseEvent
from communication.interfaces import IEventBus, IScheduler, IHealthMonitor
from communication.models import Subscription
from communication.models.heartbeat import Heartbeat
from communication.models.health_state import HealthState


# ---------------------------------------------------------------------------
# Stub implementations
# ---------------------------------------------------------------------------

class StubEventBus:
    def publish(self, event: BaseEvent) -> None: ...
    def subscribe(self, event_pattern: str, handler: Callable[[BaseEvent], None]) -> Subscription:
        return Subscription(subscriber_id="stub", event_pattern=event_pattern)
    def unsubscribe(self, subscription: Subscription) -> None: ...


class StubScheduler:
    def schedule(self, interval_seconds: float, callback: Callable[[], None]) -> str:
        return "job-1"
    def cancel(self, job_id: str) -> None: ...


class StubHealthMonitor:
    def register(self, component_name: str) -> None: ...
    def record_heartbeat(self, heartbeat: Heartbeat) -> None: ...
    def is_alive(self, component_name: str) -> bool:
        return True


class IncompleteEventBus:
    def publish(self, event: BaseEvent) -> None: ...
    def subscribe(self, event_pattern: str, handler: Callable[[BaseEvent], None]) -> Subscription:
        return Subscription(subscriber_id="x", event_pattern=event_pattern)
    # missing unsubscribe


class IncompleteScheduler:
    def schedule(self, interval_seconds: float, callback: Callable[[], None]) -> str:
        return "job-1"
    # missing cancel


class IncompleteHealthMonitor:
    def register(self, component_name: str) -> None: ...
    def record_heartbeat(self, heartbeat: Heartbeat) -> None: ...
    # missing is_alive


# ---------------------------------------------------------------------------
# IEventBus compliance
# ---------------------------------------------------------------------------

class TestIEventBusCompliance:

    def test_stub_satisfies_protocol(self) -> None:
        assert isinstance(StubEventBus(), IEventBus)

    def test_incomplete_does_not_satisfy_protocol(self) -> None:
        assert not isinstance(IncompleteEventBus(), IEventBus)

    def test_publish_signature(self) -> None:
        bus = StubEventBus()
        bus.publish(BaseEvent(event_type="test.event"))

    def test_subscribe_returns_subscription(self) -> None:
        bus = StubEventBus()
        sub = bus.subscribe("market.tick", lambda e: None)
        assert isinstance(sub, Subscription)
        assert sub.event_pattern == "market.tick"

    def test_unsubscribe_accepts_subscription(self) -> None:
        bus = StubEventBus()
        sub = bus.subscribe("market.tick", lambda e: None)
        bus.unsubscribe(sub)

    def test_plain_object_does_not_satisfy_protocol(self) -> None:
        assert not isinstance(object(), IEventBus)

    def test_none_does_not_satisfy_protocol(self) -> None:
        assert not isinstance(None, IEventBus)


# ---------------------------------------------------------------------------
# IScheduler compliance
# ---------------------------------------------------------------------------

class TestISchedulerCompliance:

    def test_stub_satisfies_protocol(self) -> None:
        assert isinstance(StubScheduler(), IScheduler)

    def test_incomplete_does_not_satisfy_protocol(self) -> None:
        assert not isinstance(IncompleteScheduler(), IScheduler)

    def test_schedule_returns_str(self) -> None:
        job_id = StubScheduler().schedule(1.0, lambda: None)
        assert isinstance(job_id, str)

    def test_cancel_accepts_job_id(self) -> None:
        scheduler = StubScheduler()
        job_id = scheduler.schedule(1.0, lambda: None)
        scheduler.cancel(job_id)

    def test_plain_object_does_not_satisfy_protocol(self) -> None:
        assert not isinstance(object(), IScheduler)


# ---------------------------------------------------------------------------
# IHealthMonitor compliance
# ---------------------------------------------------------------------------

class TestIHealthMonitorCompliance:

    def test_stub_satisfies_protocol(self) -> None:
        assert isinstance(StubHealthMonitor(), IHealthMonitor)

    def test_incomplete_does_not_satisfy_protocol(self) -> None:
        assert not isinstance(IncompleteHealthMonitor(), IHealthMonitor)

    def test_register_accepts_component_name(self) -> None:
        StubHealthMonitor().register("orion")

    def test_record_heartbeat_accepts_heartbeat(self) -> None:
        hb = Heartbeat(
            component_name="orion",
            health_state=HealthState.RUNNING,
            uptime_seconds=100,
            version="1.0.0",
        )
        StubHealthMonitor().record_heartbeat(hb)

    def test_is_alive_returns_bool(self) -> None:
        monitor = StubHealthMonitor()
        monitor.register("orion")
        assert isinstance(monitor.is_alive("orion"), bool)

    def test_plain_object_does_not_satisfy_protocol(self) -> None:
        assert not isinstance(object(), IHealthMonitor)
