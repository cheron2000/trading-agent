"""
communication.bus.rate_limiter
================================

RateLimiter — token-bucket rate limiter for EventBus publishers.

Tracks publish rate per event_type prefix (e.g. "data", "execution").
Thread-safe. Raises RateLimitExceeded when a publisher exceeds its
configured limit.

Python Version: 3.11+
"""

from __future__ import annotations

import threading
import time
from typing import ClassVar


class RateLimitExceeded(Exception):
    """Raised when a publisher exceeds its configured rate limit."""


class _TokenBucket:
    """Single token-bucket for one event prefix.

    Refills at `rate` tokens/second up to `capacity` tokens.
    Each publish consumes 1 token. Thread-safe.
    """

    def __init__(self, capacity: float, rate: float) -> None:
        self._capacity = capacity
        self._rate = rate  # tokens per second
        self._tokens = capacity  # start full
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def consume(self) -> bool:
        """Attempt to consume 1 token.

        Returns:
            True if token was available and consumed.
            False if bucket is empty (rate limit hit).
        """
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self._capacity,
                self._tokens + elapsed * self._rate,
            )
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


class RateLimiter:
    """Per-prefix token-bucket rate limiter for EventBus.

    Groups event types by their first dot-segment prefix
    (e.g. "data.feature_vector" → prefix "data") and applies
    a shared bucket per prefix.

    Usage::

        limiter = RateLimiter(default_rate=100.0, default_capacity=200.0)
        limiter.set_limit("data", rate=50.0, capacity=100.0)

        # In EventBus.publish():
        limiter.check("data.feature_vector")   # raises if over limit
    """

    # Sensible defaults: 100 events/sec, burst up to 200
    DEFAULT_RATE: ClassVar[float] = 100.0
    DEFAULT_CAPACITY: ClassVar[float] = 200.0

    def __init__(
        self,
        default_rate: float = DEFAULT_RATE,
        default_capacity: float = DEFAULT_CAPACITY,
    ) -> None:
        """
        Args:
            default_rate:     Tokens/second for any prefix without a
                              specific limit.
            default_capacity: Burst capacity for the default bucket.

        Raises:
            ValueError: If default_rate or default_capacity <= 0.
        """
        if default_rate <= 0:
            raise ValueError("default_rate must be > 0.")
        if default_capacity <= 0:
            raise ValueError("default_capacity must be > 0.")

        self._default_rate = default_rate
        self._default_capacity = default_capacity
        self._buckets: dict[str, _TokenBucket] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_limit(
        self,
        prefix: str,
        rate: float,
        capacity: float | None = None,
    ) -> None:
        """Set a custom rate limit for an event prefix.

        Args:
            prefix:   Event type prefix (e.g. "data", "execution").
            rate:     Tokens per second allowed for this prefix.
            capacity: Burst capacity. Defaults to 2× rate if not set.

        Raises:
            ValueError: If prefix is empty or rate <= 0.
        """
        if not prefix or not prefix.strip():
            raise ValueError("prefix must not be empty.")
        if rate <= 0:
            raise ValueError("rate must be > 0.")

        cap = capacity if capacity is not None else rate * 2
        with self._lock:
            self._buckets[prefix.strip()] = _TokenBucket(capacity=cap, rate=rate)

    # ------------------------------------------------------------------
    # Runtime check
    # ------------------------------------------------------------------

    def check(self, event_type: str) -> None:
        """Check whether publishing event_type is within rate limit.

        Extracts the prefix (first dot-segment) from event_type and
        consumes one token from the matching bucket.

        Args:
            event_type: Full event type string (e.g. "data.feature_vector").

        Raises:
            RateLimitExceeded: If the bucket for this prefix is empty.
            ValueError:        If event_type is empty.
        """
        if not event_type or not event_type.strip():
            raise ValueError("event_type must not be empty.")

        prefix = event_type.split(".")[0]
        bucket = self._get_or_create_bucket(prefix)

        if not bucket.consume():
            raise RateLimitExceeded(
                f"Rate limit exceeded for event prefix '{prefix}' "
                f"(event_type='{event_type}'). "
                f"Slow down the publisher or increase the limit via "
                f"RateLimiter.set_limit('{prefix}', rate=...)."
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_or_create_bucket(self, prefix: str) -> _TokenBucket:
        with self._lock:
            if prefix not in self._buckets:
                self._buckets[prefix] = _TokenBucket(
                    capacity=self._default_capacity,
                    rate=self._default_rate,
                )
            return self._buckets[prefix]
