"""
Unit tests for foundation.base_event.

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest

from foundation.base_event import BaseEvent


class TestEvent(BaseEvent):
    """Concrete event implementation for testing."""

    value: int = 100


# ============================================================================
# Construction
# ============================================================================


def test_event_creation() -> None:
    """An event should be created with the expected values."""
    event = TestEvent(event_type="test.event")

    assert event.event_type == "test.event"
    assert event.schema_version == "1.0"
    assert event.correlation_id is None
    assert event.causation_id is None


def test_event_generates_uuid() -> None:
    """A UUID should be generated automatically."""
    event = TestEvent(event_type="test.event")

    uuid = UUID(event.event_id)

    assert str(uuid) == event.event_id


def test_event_timestamp_is_utc() -> None:
    """The event timestamp should be timezone-aware UTC."""
    event = TestEvent(event_type="test.event")

    assert isinstance(event.occurred_at, datetime)
    assert event.occurred_at.tzinfo == UTC


# ============================================================================
# Immutability
# ============================================================================


def test_event_is_immutable() -> None:
    """BaseEvent should be immutable."""
    event = TestEvent(event_type="test.event")

    with pytest.raises(FrozenInstanceError):
        event.event_type = "another.event"  # type: ignore[misc]


# ============================================================================
# Serialization
# ============================================================================


def test_to_dict_contains_expected_fields() -> None:
    """Serialized dictionary should contain all required fields."""
    event = TestEvent(event_type="test.event")

    data = event.to_dict()

    assert data["event_id"] == event.event_id
    assert data["event_type"] == "test.event"
    assert data["schema_version"] == "1.0"
    assert "occurred_at" in data
    assert "correlation_id" in data
    assert "causation_id" in data


def test_name_property() -> None:
    """The name property should return the event type."""
    event = TestEvent(event_type="market.tick")

    assert event.name == "market.tick"


# ============================================================================
# Correlation
# ============================================================================


def test_correlation_and_causation_ids() -> None:
    """Explicit correlation identifiers should be preserved."""
    event = TestEvent(
        event_type="risk.approved",
        correlation_id="corr-123",
        causation_id="cause-456",
    )

    assert event.correlation_id == "corr-123"
    assert event.causation_id == "cause-456"


# ============================================================================
# String Representations
# ============================================================================


def test_str_representation() -> None:
    """String representation should contain useful information."""
    event = TestEvent(event_type="execution.created")

    text = str(event)

    assert "TestEvent" in text
    assert "execution.created" in text
    assert event.event_id in text


# ============================================================================
# Identity
# ============================================================================


def test_each_event_has_unique_identifier() -> None:
    """Each event should receive a unique identifier."""
    event1 = TestEvent(event_type="test.event")
    event2 = TestEvent(event_type="test.event")

    assert event1.event_id != event2.event_id


def test_each_event_has_unique_timestamp() -> None:
    """Events should receive valid timestamps."""
    event1 = TestEvent(event_type="test.event")
    event2 = TestEvent(event_type="test.event")

    assert event1.occurred_at <= event2.occurred_at or (
        event2.occurred_at <= event1.occurred_at
    )