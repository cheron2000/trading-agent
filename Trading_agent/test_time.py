"""
Unit tests for foundation.utils.time.

Python: 3.13+
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from foundation.utils.time import (
    add_duration,
    elapsed,
    from_iso8601,
    from_unix_timestamp,
    is_expired,
    seconds_between,
    subtract_duration,
    to_iso8601,
    unix_timestamp,
    utc_now,
    utc_today,
)


# ============================================================================
# UTC Time
# ============================================================================


def test_utc_now_returns_utc_datetime() -> None:
    """utc_now() should return a timezone-aware UTC datetime."""
    now = utc_now()

    assert isinstance(now, datetime)
    assert now.tzinfo == UTC


def test_utc_today_returns_midnight() -> None:
    """utc_today() should return today's UTC midnight."""
    today = utc_today()

    assert today.hour == 0
    assert today.minute == 0
    assert today.second == 0
    assert today.microsecond == 0
    assert today.tzinfo == UTC


# ============================================================================
# ISO-8601
# ============================================================================


def test_to_iso8601() -> None:
    """Datetime should serialize to ISO-8601."""
    value = datetime(2026, 7, 1, 12, 30, tzinfo=UTC)

    assert to_iso8601(value) == value.isoformat()


def test_from_iso8601() -> None:
    """ISO-8601 string should deserialize correctly."""
    value = "2026-07-01T12:30:00+00:00"

    parsed = from_iso8601(value)

    assert parsed.year == 2026
    assert parsed.month == 7
    assert parsed.day == 1
    assert parsed.tzinfo == UTC


def test_to_iso8601_rejects_naive_datetime() -> None:
    """Naive datetimes should raise ValueError."""
    with pytest.raises(ValueError):
        to_iso8601(datetime.now())


def test_from_iso8601_rejects_naive_datetime() -> None:
    """Naive ISO strings should raise ValueError."""
    with pytest.raises(ValueError):
        from_iso8601("2026-07-01T12:00:00")


# ============================================================================
# Unix Timestamp
# ============================================================================


def test_unix_timestamp_round_trip() -> None:
    """Unix timestamp conversion should be reversible."""
    original = utc_now()

    timestamp = unix_timestamp(original)
    restored = from_unix_timestamp(timestamp)

    assert abs((restored - original).total_seconds()) < 0.001


# ============================================================================
# Durations
# ============================================================================


def test_elapsed() -> None:
    """elapsed() should compute the correct duration."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(seconds=30)

    assert elapsed(start, end) == timedelta(seconds=30)


def test_seconds_between() -> None:
    """seconds_between() should return elapsed seconds."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(minutes=2)

    assert seconds_between(start, end) == 120


# ============================================================================
# Expiration
# ============================================================================


def test_is_expired_true() -> None:
    """Expired timestamps should return True."""
    created = utc_now() - timedelta(minutes=10)

    assert is_expired(
        created,
        timedelta(minutes=5),
    )


def test_is_expired_false() -> None:
    """Fresh timestamps should return False."""
    created = utc_now()

    assert not is_expired(
        created,
        timedelta(minutes=5),
    )


# ============================================================================
# Duration Arithmetic
# ============================================================================


def test_add_duration() -> None:
    """Duration should be added correctly."""
    start = datetime(2026, 1, 1, tzinfo=UTC)

    result = add_duration(
        start,
        timedelta(days=1),
    )

    assert result.day == 2


def test_subtract_duration() -> None:
    """Duration should be subtracted correctly."""
    start = datetime(2026, 1, 2, tzinfo=UTC)

    result = subtract_duration(
        start,
        timedelta(days=1),
    )

    assert result.day == 1