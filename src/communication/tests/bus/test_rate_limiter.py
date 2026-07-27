"""
Unit tests for communication.bus.rate_limiter.RateLimiter
and EventBus rate limiting integration.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from communication.bus.event_bus import EventBus
from communication.bus.rate_limiter import RateLimiter, RateLimitExceeded
from foundation.base_event import BaseEvent

# ---------------------------------------------------------------------------
# RateLimiter construction
# ---------------------------------------------------------------------------


class TestRateLimiterInit:

    def test_default_construction(self) -> None:
        rl = RateLimiter()
        assert rl.DEFAULT_RATE == 100.0
        assert rl.DEFAULT_CAPACITY == 200.0

    def test_custom_rate_and_capacity(self) -> None:
        rl = RateLimiter(default_rate=10.0, default_capacity=20.0)
        # Should not raise
        for _ in range(20):
            rl.check("data.tick")

    def test_zero_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="default_rate"):
            RateLimiter(default_rate=0)

    def test_negative_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="default_rate"):
            RateLimiter(default_rate=-1.0)

    def test_zero_capacity_raises(self) -> None:
        with pytest.raises(ValueError, match="default_capacity"):
            RateLimiter(default_capacity=0)


# ---------------------------------------------------------------------------
# set_limit()
# ---------------------------------------------------------------------------


class TestSetLimit:

    def test_set_limit_valid(self) -> None:
        rl = RateLimiter()
        rl.set_limit("data", rate=10.0, capacity=20.0)  # no raise

    def test_set_limit_empty_prefix_raises(self) -> None:
        rl = RateLimiter()
        with pytest.raises(ValueError, match="prefix"):
            rl.set_limit("", rate=10.0)

    def test_set_limit_zero_rate_raises(self) -> None:
        rl = RateLimiter()
        with pytest.raises(ValueError, match="rate"):
            rl.set_limit("data", rate=0)

    def test_set_limit_default_capacity_is_2x_rate(self) -> None:
        rl = RateLimiter()
        # capacity defaults to 2x rate — bucket should allow 2x rate bursts
        rl.set_limit("data", rate=5.0)
        # 10 calls should succeed (capacity = 10)
        for _ in range(10):
            rl.check("data.tick")
        # 11th should fail
        with pytest.raises(RateLimitExceeded):
            rl.check("data.tick")


# ---------------------------------------------------------------------------
# check()
# ---------------------------------------------------------------------------


class TestCheck:

    def test_check_empty_event_type_raises(self) -> None:
        rl = RateLimiter()
        with pytest.raises(ValueError, match="event_type"):
            rl.check("")

    def test_check_within_limit_passes(self) -> None:
        rl = RateLimiter(default_rate=100.0, default_capacity=10.0)
        for _ in range(10):
            rl.check("data.feature_vector")  # no raise

    def test_check_exceeds_limit_raises(self) -> None:
        rl = RateLimiter(default_rate=100.0, default_capacity=3.0)
        for _ in range(3):
            rl.check("data.tick")
        with pytest.raises(RateLimitExceeded, match="data"):
            rl.check("data.tick")

    def test_check_uses_first_segment_as_prefix(self) -> None:
        rl = RateLimiter()
        rl.set_limit("execution", rate=2.0, capacity=2.0)
        rl.check("execution.fill")
        rl.check("execution.order")
        with pytest.raises(RateLimitExceeded):
            rl.check("execution.fill")

    def test_different_prefixes_have_independent_buckets(self) -> None:
        rl = RateLimiter(default_rate=100.0, default_capacity=2.0)
        rl.check("data.tick")
        rl.check("data.tick")
        # data bucket empty — but intelligence bucket is fresh
        rl.check("intelligence.decision")  # no raise

    def test_bucket_refills_over_time(self) -> None:
        rl = RateLimiter(default_rate=100.0, default_capacity=1.0)
        rl.check("data.tick")  # consume the 1 token
        with pytest.raises(RateLimitExceeded):
            rl.check("data.tick")
        time.sleep(0.02)  # wait 20ms — refills 2 tokens at 100/sec
        rl.check("data.tick")  # should pass now

    def test_event_type_without_dot_uses_full_string_as_prefix(self) -> None:
        rl = RateLimiter(default_rate=100.0, default_capacity=1.0)
        rl.check("heartbeat")
        with pytest.raises(RateLimitExceeded):
            rl.check("heartbeat")


# ---------------------------------------------------------------------------
# EventBus + RateLimiter integration
# ---------------------------------------------------------------------------


class TestEventBusRateLimiting:

    def test_eventbus_without_rate_limiter_works_normally(self) -> None:
        bus = EventBus()
        received: list[Any] = []
        bus.subscribe("data.*", received.append)
        for _ in range(500):
            bus.publish(BaseEvent(event_type="data.tick"))
        assert len(received) == 500

    def test_eventbus_with_rate_limiter_blocks_excess(self) -> None:
        rl = RateLimiter(default_rate=100.0, default_capacity=5.0)
        bus = EventBus(rate_limiter=rl)
        received: list[Any] = []
        bus.subscribe("data.*", received.append)

        # First 5 should pass
        for _ in range(5):
            bus.publish(BaseEvent(event_type="data.tick"))
        assert len(received) == 5

        # 6th should raise
        with pytest.raises(RateLimitExceeded):
            bus.publish(BaseEvent(event_type="data.tick"))

    def test_eventbus_rate_limiter_per_prefix(self) -> None:
        rl = RateLimiter(default_rate=100.0, default_capacity=2.0)
        bus = EventBus(rate_limiter=rl)

        bus.publish(BaseEvent(event_type="data.tick"))
        bus.publish(BaseEvent(event_type="data.tick"))

        # data exhausted, but execution is fresh
        bus.publish(BaseEvent(event_type="execution.fill"))  # no raise

        with pytest.raises(RateLimitExceeded):
            bus.publish(BaseEvent(event_type="data.tick"))

    def test_eventbus_none_event_still_raises_value_error(self) -> None:
        rl = RateLimiter()
        bus = EventBus(rate_limiter=rl)
        with pytest.raises(ValueError, match="event must not be None"):
            bus.publish(None)  # type: ignore

    def test_eventbus_rate_limit_error_message_contains_prefix(self) -> None:
        rl = RateLimiter(default_rate=100.0, default_capacity=1.0)
        bus = EventBus(rate_limiter=rl)
        bus.publish(BaseEvent(event_type="intelligence.decision"))
        with pytest.raises(RateLimitExceeded, match="intelligence"):
            bus.publish(BaseEvent(event_type="intelligence.decision"))
