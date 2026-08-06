"""
Unit tests for communication.bus.event_bus.EventBus.
"""

from __future__ import annotations

import threading
import pytest

from foundation.base_event import BaseEvent
from communication.bus import EventBus
from communication.interfaces import IEventBus
from communication.models import Subscription


def make_event(event_type: str = "market.tick") -> BaseEvent:
    return BaseEvent(event_type=event_type)


class TestEventBusProtocolCompliance:

    def test_satisfies_ieventbus_protocol(self) -> None:
        assert isinstance(EventBus(), IEventBus)


class TestEventBusPublish:

    def test_publish_calls_matching_handler(self) -> None:
        bus = EventBus()
        received = []
        bus.subscribe("market.tick", received.append)
        bus.publish(make_event("market.tick"))
        assert len(received) == 1
        assert received[0].event_type == "market.tick"

    def test_publish_none_raises(self) -> None:
        bus = EventBus()
        with pytest.raises(ValueError):
            bus.publish(None)  # type: ignore

    def test_publish_no_subscribers_does_not_raise(self) -> None:
        bus = EventBus()
        bus.publish(make_event("market.tick"))  # must not raise

    def test_publish_calls_multiple_handlers(self) -> None:
        bus = EventBus()
        calls: list[str] = []
        bus.subscribe("market.tick", lambda e: calls.append("h1"))
        bus.subscribe("market.tick", lambda e: calls.append("h2"))
        bus.publish(make_event("market.tick"))
        assert sorted(calls) == ["h1", "h2"]

    def test_publish_does_not_call_non_matching_handler(self) -> None:
        bus = EventBus()
        received = []
        bus.subscribe("execution.order", received.append)
        bus.publish(make_event("market.tick"))
        assert received == []


class TestEventBusWildcard:

    def test_wildcard_star_matches_any_suffix(self) -> None:
        bus = EventBus()
        received = []
        bus.subscribe("market.*", received.append)
        bus.publish(make_event("market.tick"))
        bus.publish(make_event("market.data"))
        assert len(received) == 2

    def test_wildcard_star_matches_deeper_segments(self) -> None:
        bus = EventBus()
        received = []
        bus.subscribe("market.*", received.append)
        bus.publish(make_event("market.tick.extra"))
        # fnmatch: "market.*" DOES match "market.tick.extra" — * matches any chars including dots
        assert len(received) == 1

    def test_global_wildcard_matches_all(self) -> None:
        bus = EventBus()
        received = []
        bus.subscribe("*", received.append)
        bus.publish(make_event("market.tick"))
        bus.publish(make_event("execution.order"))
        assert len(received) == 2

    def test_exact_pattern_does_not_match_wildcard_event(self) -> None:
        bus = EventBus()
        received = []
        bus.subscribe("market.tick", received.append)
        bus.publish(make_event("market.data"))
        assert received == []


class TestEventBusSubscribeUnsubscribe:

    def test_subscribe_returns_subscription(self) -> None:
        bus = EventBus()
        sub = bus.subscribe("market.tick", lambda e: None)
        assert isinstance(sub, Subscription)
        assert sub.event_pattern == "market.tick"
        assert sub.enabled is True

    def test_subscribe_empty_pattern_raises(self) -> None:
        bus = EventBus()
        with pytest.raises(ValueError):
            bus.subscribe("", lambda e: None)

    def test_subscribe_whitespace_pattern_raises(self) -> None:
        bus = EventBus()
        with pytest.raises(ValueError):
            bus.subscribe("   ", lambda e: None)

    def test_unsubscribe_stops_delivery(self) -> None:
        bus = EventBus()
        received = []
        sub = bus.subscribe("market.tick", received.append)
        bus.unsubscribe(sub)
        bus.publish(make_event("market.tick"))
        assert received == []

    def test_unsubscribe_unknown_subscription_is_noop(self) -> None:
        bus = EventBus()
        sub = Subscription(subscriber_id="ghost-id", event_pattern="market.tick")
        bus.unsubscribe(sub)  # must not raise

    def test_subscription_count_increments(self) -> None:
        bus = EventBus()
        assert bus.subscription_count == 0
        bus.subscribe("a.b", lambda e: None)
        bus.subscribe("c.d", lambda e: None)
        assert bus.subscription_count == 2

    def test_subscription_count_decrements_on_unsubscribe(self) -> None:
        bus = EventBus()
        sub = bus.subscribe("a.b", lambda e: None)
        bus.unsubscribe(sub)
        assert bus.subscription_count == 0

    def test_clear_removes_all_subscriptions(self) -> None:
        bus = EventBus()
        bus.subscribe("a.b", lambda e: None)
        bus.subscribe("c.d", lambda e: None)
        bus.clear()
        assert bus.subscription_count == 0


class TestEventBusThreadSafety:

    def test_concurrent_publish_and_subscribe(self) -> None:
        bus = EventBus()
        received = []
        lock = threading.Lock()

        def publisher() -> None:
            for _ in range(50):
                bus.publish(make_event("market.tick"))

        def subscriber() -> None:
            def handler(e: BaseEvent) -> None:
                with lock:
                    received.append(e)

            bus.subscribe("market.tick", handler)

        threads = [threading.Thread(target=subscriber) for _ in range(3)]
        threads += [threading.Thread(target=publisher) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # No assertion on count — just must not raise or deadlock
