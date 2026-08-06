"""
Unit tests for communication.models.event_envelope.
"""

from __future__ import annotations

import pytest

from foundation.base_event import BaseEvent
from communication.models import EventEnvelope, EventMetadata, EventPriority


def make_event() -> BaseEvent:
    return BaseEvent(event_type="test.event")


def make_metadata() -> EventMetadata:
    return EventMetadata(source_component="orion")


class TestEventEnvelope:

    def test_valid_creation(self) -> None:
        e = make_event()
        m = make_metadata()
        env = EventEnvelope(event=e, metadata=m, priority=EventPriority.NORMAL)
        assert env.event is e
        assert env.metadata is m
        assert env.priority == EventPriority.NORMAL

    def test_none_event_raises(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            EventEnvelope(event=None, metadata=make_metadata(), priority=EventPriority.NORMAL)  # type: ignore

    def test_none_metadata_raises(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            EventEnvelope(event=make_event(), metadata=None, priority=EventPriority.NORMAL)  # type: ignore

    def test_invalid_priority_raises(self) -> None:
        with pytest.raises(TypeError):
            EventEnvelope(event=make_event(), metadata=make_metadata(), priority="high")  # type: ignore

    def test_created_at_delegates_to_event(self) -> None:
        e = make_event()
        env = EventEnvelope(
            event=e, metadata=make_metadata(), priority=EventPriority.NORMAL
        )
        assert env.created_at == e.occurred_at

    def test_event_type_property(self) -> None:
        env = EventEnvelope(
            event=make_event(), metadata=make_metadata(), priority=EventPriority.NORMAL
        )
        assert env.event_type == "test.event"

    def test_event_id_property(self) -> None:
        e = make_event()
        env = EventEnvelope(
            event=e, metadata=make_metadata(), priority=EventPriority.NORMAL
        )
        assert env.event_id == e.event_id

    def test_source_component_property(self) -> None:
        env = EventEnvelope(
            event=make_event(), metadata=make_metadata(), priority=EventPriority.NORMAL
        )
        assert env.source_component == "orion"

    def test_target_component_none_by_default(self) -> None:
        env = EventEnvelope(
            event=make_event(), metadata=make_metadata(), priority=EventPriority.NORMAL
        )
        assert env.target_component is None

    def test_retry_count_default(self) -> None:
        env = EventEnvelope(
            event=make_event(), metadata=make_metadata(), priority=EventPriority.NORMAL
        )
        assert env.retry_count == 0

    def test_is_retry_false(self) -> None:
        env = EventEnvelope(
            event=make_event(), metadata=make_metadata(), priority=EventPriority.NORMAL
        )
        assert env.is_retry is False

    def test_is_retry_true(self) -> None:
        m = EventMetadata(source_component="orion", retry_count=2)
        env = EventEnvelope(
            event=make_event(), metadata=m, priority=EventPriority.NORMAL
        )
        assert env.is_retry is True

    def test_transport_id_none_by_default(self) -> None:
        env = EventEnvelope(
            event=make_event(), metadata=make_metadata(), priority=EventPriority.NORMAL
        )
        assert env.transport_id is None

    def test_immutability(self) -> None:
        env = EventEnvelope(
            event=make_event(), metadata=make_metadata(), priority=EventPriority.NORMAL
        )
        with pytest.raises((AttributeError, TypeError)):
            env.priority = EventPriority.HIGH  # type: ignore[misc]

    def test_to_dict(self) -> None:
        env = EventEnvelope(
            event=make_event(),
            metadata=make_metadata(),
            priority=EventPriority.CRITICAL,
        )
        d = env.to_dict()
        assert "event" in d
        assert "metadata" in d
        assert d["priority"] == EventPriority.CRITICAL.value

    def test_to_dict_event_keys(self) -> None:
        env = EventEnvelope(
            event=make_event(), metadata=make_metadata(), priority=EventPriority.NORMAL
        )
        d = env.to_dict()
        assert "event_id" in d["event"]
        assert "event_type" in d["event"]
