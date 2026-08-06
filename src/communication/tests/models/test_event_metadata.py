"""
Unit tests for communication.models.event_metadata.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from communication.models import EventMetadata, EventPriority


class TestEventMetadata:

    def test_valid_creation_defaults(self) -> None:
        m = EventMetadata(source_component="orion")
        assert m.source_component == "orion"
        assert m.priority == EventPriority.NORMAL
        assert m.retry_count == 0
        assert m.target_component is None
        assert m.transport_id is None

    def test_valid_creation_all_fields(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        m = EventMetadata(
            source_component="orion",
            priority=EventPriority.HIGH,
            retry_count=3,
            target_component="athena",
            transport_id="t-123",
            created_at=ts,
        )
        assert m.priority == EventPriority.HIGH
        assert m.retry_count == 3
        assert m.target_component == "athena"
        assert m.transport_id == "t-123"
        assert m.created_at == ts

    def test_empty_source_component_raises(self) -> None:
        with pytest.raises(ValueError):
            EventMetadata(source_component="")

    def test_whitespace_source_component_raises(self) -> None:
        with pytest.raises(ValueError):
            EventMetadata(source_component="   ")

    def test_source_component_too_long_raises(self) -> None:
        with pytest.raises(ValueError):
            EventMetadata(source_component="a" * 256)

    def test_empty_target_component_raises(self) -> None:
        with pytest.raises(ValueError):
            EventMetadata(source_component="x", target_component="")

    def test_target_component_too_long_raises(self) -> None:
        with pytest.raises(ValueError):
            EventMetadata(source_component="x", target_component="a" * 256)

    def test_empty_transport_id_raises(self) -> None:
        with pytest.raises(ValueError):
            EventMetadata(source_component="x", transport_id="")

    def test_transport_id_too_long_raises(self) -> None:
        with pytest.raises(ValueError):
            EventMetadata(source_component="x", transport_id="a" * 256)

    def test_negative_retry_count_raises(self) -> None:
        with pytest.raises(ValueError):
            EventMetadata(source_component="x", retry_count=-1)

    def test_retry_count_exceeds_limit_raises(self) -> None:
        with pytest.raises(ValueError):
            EventMetadata(source_component="x", retry_count=10_001)

    def test_is_retry_event(self) -> None:
        assert EventMetadata(source_component="x", retry_count=1).is_retry_event is True
        assert (
            EventMetadata(source_component="x", retry_count=0).is_retry_event is False
        )

    def test_is_routing_targeted(self) -> None:
        assert (
            EventMetadata(
                source_component="x", target_component="y"
            ).is_routing_targeted
            is True
        )
        assert EventMetadata(source_component="x").is_routing_targeted is False

    def test_is_transport_assigned(self) -> None:
        assert (
            EventMetadata(source_component="x", transport_id="t1").is_transport_assigned
            is True
        )
        assert EventMetadata(source_component="x").is_transport_assigned is False

    def test_created_at_is_per_instance(self) -> None:
        m1 = EventMetadata(source_component="x")
        m2 = EventMetadata(source_component="x")
        assert m1.created_at <= m2.created_at

    def test_immutability(self) -> None:
        m = EventMetadata(source_component="x")
        with pytest.raises((AttributeError, TypeError)):
            m.source_component = "y"  # type: ignore[misc]

    def test_equality(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        m1 = EventMetadata(source_component="x", created_at=ts)
        m2 = EventMetadata(source_component="x", created_at=ts)
        assert m1 == m2

    def test_inequality(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        m1 = EventMetadata(source_component="x", created_at=ts)
        m2 = EventMetadata(source_component="y", created_at=ts)
        assert m1 != m2

    def test_hashable(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        m = EventMetadata(source_component="x", created_at=ts)
        assert isinstance(hash(m), int)

    def test_to_dict(self) -> None:
        ts = datetime(2025, 6, 1, tzinfo=timezone.utc)
        m = EventMetadata(
            source_component="orion", priority=EventPriority.LOW, created_at=ts
        )
        d = m.to_dict()
        assert d["source_component"] == "orion"
        assert d["priority"] == EventPriority.LOW.value
        assert d["retry_count"] == 0
        assert "created_at" in d

    def test_str_representation(self) -> None:
        m = EventMetadata(source_component="orion")
        assert "orion" in str(m)
