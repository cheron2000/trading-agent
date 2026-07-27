"""
Unit tests for communication.models.subscription.
"""

from __future__ import annotations

import pytest

from communication.models import EventPriority, Subscription


class TestSubscription:

    def test_valid_creation(self) -> None:
        s = Subscription(subscriber_id="svc-a", event_pattern="market.data.received")
        assert s.subscriber_id == "svc-a"
        assert s.event_pattern == "market.data.received"
        assert s.priority == EventPriority.NORMAL
        assert s.enabled is True
        assert s.filter_expression is None

    def test_custom_priority_and_filter(self) -> None:
        s = Subscription(
            subscriber_id="svc-b",
            event_pattern="execution.order.*",
            priority=EventPriority.HIGH,
            filter_expression="symbol=AAPL",
        )
        assert s.priority == EventPriority.HIGH
        assert s.filter_expression == "symbol=AAPL"

    def test_disabled_subscription(self) -> None:
        s = Subscription(subscriber_id="svc-c", event_pattern="risk.*", enabled=False)
        assert s.is_enabled is False

    def test_has_filter(self) -> None:
        s = Subscription(
            subscriber_id="x", event_pattern="a.b", filter_expression="k=v"
        )
        assert s.has_filter is True

    def test_no_filter(self) -> None:
        s = Subscription(subscriber_id="x", event_pattern="a.b")
        assert s.has_filter is False

    def test_matches_exact_true(self) -> None:
        s = Subscription(subscriber_id="x", event_pattern="market.tick")
        assert s.matches_exact("market.tick") is True

    def test_matches_exact_false(self) -> None:
        s = Subscription(subscriber_id="x", event_pattern="market.tick")
        assert s.matches_exact("market.other") is False

    def test_empty_subscriber_id_raises(self) -> None:
        with pytest.raises(ValueError):
            Subscription(subscriber_id="", event_pattern="a.b")

    def test_whitespace_subscriber_id_raises(self) -> None:
        with pytest.raises(ValueError):
            Subscription(subscriber_id="   ", event_pattern="a.b")

    def test_empty_event_pattern_raises(self) -> None:
        with pytest.raises(ValueError):
            Subscription(subscriber_id="x", event_pattern="")

    def test_whitespace_in_event_pattern_raises(self) -> None:
        with pytest.raises(ValueError):
            Subscription(subscriber_id="x", event_pattern="market data")

    def test_double_dot_in_event_pattern_raises(self) -> None:
        with pytest.raises(ValueError):
            Subscription(subscriber_id="x", event_pattern="market..data")

    def test_empty_filter_expression_raises(self) -> None:
        with pytest.raises(ValueError):
            Subscription(subscriber_id="x", event_pattern="a.b", filter_expression="")

    def test_subscriber_id_max_length_raises(self) -> None:
        with pytest.raises(ValueError):
            Subscription(subscriber_id="a" * 256, event_pattern="a.b")

    def test_event_pattern_max_length_raises(self) -> None:
        with pytest.raises(ValueError):
            Subscription(subscriber_id="x", event_pattern="a" * 256)

    def test_immutability(self) -> None:
        s = Subscription(subscriber_id="x", event_pattern="a.b")
        with pytest.raises((AttributeError, TypeError)):
            s.enabled = False  # type: ignore[misc]

    def test_hashable(self) -> None:
        s1 = Subscription(subscriber_id="x", event_pattern="a.b")
        s2 = Subscription(subscriber_id="x", event_pattern="a.b")
        assert hash(s1) == hash(s2)
        assert {s1, s2} == {s1}

    def test_to_dict(self) -> None:
        s = Subscription(
            subscriber_id="svc", event_pattern="a.b", priority=EventPriority.LOW
        )
        d = s.to_dict()
        assert d["subscriber_id"] == "svc"
        assert d["event_pattern"] == "a.b"
        assert d["priority"] == EventPriority.LOW.value
        assert d["enabled"] is True
        assert d["filter_expression"] is None

    def test_str_representation(self) -> None:
        s = Subscription(subscriber_id="svc", event_pattern="a.b")
        assert "svc" in str(s)
        assert "a.b" in str(s)
