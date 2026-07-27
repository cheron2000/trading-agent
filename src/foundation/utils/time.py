"""
Time utilities for the AI Trading Operating System.

This module provides standardized UTC time operations used throughout
the Foundation Layer. All timestamps in the system must be timezone-aware
and expressed in UTC.

Features:
    - Timezone-aware UTC timestamps
    - ISO 8601 formatting and parsing
    - Unix timestamp conversion
    - Duration calculation
    - Elapsed time measurement

Python: 3.13+
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    """Return the current UTC time.

    Returns:
        A timezone-aware UTC datetime.
    """
    return datetime.now(UTC)


def utc_today() -> datetime:
    """Return today's UTC date at midnight.

    Returns:
        A timezone-aware datetime representing the start of the current UTC day.
    """
    now = utc_now()
    return datetime(
        year=now.year,
        month=now.month,
        day=now.day,
        tzinfo=UTC,
    )


def to_iso8601(value: datetime) -> str:
    """Convert a datetime to an ISO 8601 string.

    Args:
        value:
            Timezone-aware datetime.

    Returns:
        ISO 8601 formatted string.

    Raises:
        ValueError:
            If the datetime is timezone-naive.
    """
    if value.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware.")

    return value.isoformat()


def from_iso8601(value: str) -> datetime:
    """Parse an ISO 8601 datetime string.

    Args:
        value:
            ISO 8601 datetime string.

    Returns:
        Parsed timezone-aware datetime.

    Raises:
        ValueError:
            If the string is invalid or timezone information is missing.
    """
    dt = datetime.fromisoformat(value)

    if dt.tzinfo is None:
        raise ValueError("Datetime string must contain timezone information.")

    return dt.astimezone(UTC)


def unix_timestamp(value: datetime) -> float:
    """Convert a datetime to a Unix timestamp.

    Args:
        value:
            Timezone-aware datetime.

    Returns:
        Unix timestamp in seconds.

    Raises:
        ValueError:
            If the datetime is timezone-naive.
    """
    if value.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware.")

    return value.timestamp()


def from_unix_timestamp(timestamp: float) -> datetime:
    """Convert a Unix timestamp to a UTC datetime.

    Args:
        timestamp:
            Unix timestamp in seconds.

    Returns:
        Timezone-aware UTC datetime.
    """
    return datetime.fromtimestamp(timestamp, UTC)


def elapsed(start: datetime, end: datetime | None = None) -> timedelta:
    """Calculate elapsed time.

    Args:
        start:
            Start time.
        end:
            End time. If omitted, the current UTC time is used.

    Returns:
        Time difference as a timedelta.

    Raises:
        ValueError:
            If either datetime is timezone-naive.
    """
    if start.tzinfo is None:
        raise ValueError("Start time must be timezone-aware.")

    if end is None:
        end = utc_now()

    if end.tzinfo is None:
        raise ValueError("End time must be timezone-aware.")

    return end - start


def seconds_between(start: datetime, end: datetime) -> float:
    """Return the number of seconds between two datetimes.

    Args:
        start:
            Start time.
        end:
            End time.

    Returns:
        Duration in seconds.
    """
    return elapsed(start, end).total_seconds()


def is_expired(
    created_at: datetime,
    timeout: timedelta,
) -> bool:
    """Determine whether a timeout has expired.

    Args:
        created_at:
            Object creation time.
        timeout:
            Maximum allowed age.

    Returns:
        True if the timeout has expired, otherwise False.
    """
    return elapsed(created_at) >= timeout


def add_duration(
    value: datetime,
    duration: timedelta,
) -> datetime:
    """Add a duration to a datetime.

    Args:
        value:
            Base datetime.
        duration:
            Duration to add.

    Returns:
        Updated datetime.
    """
    return value + duration


def subtract_duration(
    value: datetime,
    duration: timedelta,
) -> datetime:
    """Subtract a duration from a datetime.

    Args:
        value:
            Base datetime.
        duration:
            Duration to subtract.

    Returns:
        Updated datetime.
    """
    return value - duration
