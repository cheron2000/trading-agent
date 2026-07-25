"""
Unit tests for foundation.utils.serialization.

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from foundation.exceptions import (
    DeserializationError,
    SerializationError,
)
from foundation.utils.serialization import (
    clone,
    from_json,
    read_json,
    to_json,
    write_json,
)


@dataclass(frozen=True)
class SampleObject:
    """Simple dataclass used for serialization tests."""

    name: str
    value: int


# ============================================================================
# to_json
# ============================================================================


def test_to_json_serializes_dictionary() -> None:
    """Dictionary objects should serialize correctly."""
    result = to_json({"name": "atlas", "value": 10})

    assert isinstance(result, str)
    assert '"name"' in result
    assert '"atlas"' in result


def test_to_json_serializes_dataclass() -> None:
    """Dataclasses should serialize correctly."""
    obj = SampleObject(name="test", value=100)

    result = to_json(obj)

    assert '"name"' in result
    assert '"test"' in result


def test_to_json_serializes_datetime() -> None:
    """Datetime objects should serialize using ISO-8601."""
    result = to_json(
        {"time": datetime(2026, 1, 1, tzinfo=UTC)}
    )

    assert "2026-01-01T00:00:00+00:00" in result


def test_to_json_serializes_uuid() -> None:
    """UUID objects should serialize as strings."""
    value = uuid4()

    result = to_json({"id": value})

    assert str(value) in result


def test_to_json_serializes_path() -> None:
    """Path objects should serialize as strings."""
    result = to_json({"path": Path("/tmp/example")})

    assert "/tmp/example" in result


def test_to_json_invalid_object() -> None:
    """Unsupported objects should raise SerializationError."""

    class Unsupported:
        pass

    with pytest.raises(SerializationError):
        to_json(Unsupported())


# ============================================================================
# from_json
# ============================================================================


def test_from_json_returns_dictionary() -> None:
    """Valid JSON should deserialize correctly."""
    data = from_json('{"name":"atlas","value":1}')

    assert data["name"] == "atlas"
    assert data["value"] == 1


def test_from_json_invalid_json() -> None:
    """Invalid JSON should raise DeserializationError."""
    with pytest.raises(DeserializationError):
        from_json("{invalid}")


def test_from_json_requires_dictionary() -> None:
    """Top-level JSON must be a dictionary."""
    with pytest.raises(DeserializationError):
        from_json("[1,2,3]")


# ============================================================================
# File Operations
# ============================================================================


def test_write_json_creates_file(tmp_path: Path) -> None:
    """write_json() should create the destination file."""
    file_path = tmp_path / "example.json"

    write_json(
        file_path,
        {"name": "atlas"},
    )

    assert file_path.exists()


def test_read_json_reads_file(tmp_path: Path) -> None:
    """read_json() should return the stored dictionary."""
    file_path = tmp_path / "example.json"

    write_json(
        file_path,
        {"value": 42},
    )

    data = read_json(file_path)

    assert data["value"] == 42


def test_read_json_missing_file() -> None:
    """Missing files should raise DeserializationError."""
    with pytest.raises(DeserializationError):
        read_json("missing.json")


# ============================================================================
# clone
# ============================================================================


def test_clone_returns_equal_copy() -> None:
    """clone() should return an equivalent object."""
    original = {
        "name": "atlas",
        "numbers": [1, 2, 3],
    }

    copied = clone(original)

    assert copied == original
    assert copied is not original


def test_clone_deep_copies_nested_objects() -> None:
    """Nested objects should be copied."""
    original = {
        "nested": {
            "value": 10,
        }
    }

    copied = clone(original)

    copied["nested"]["value"] = 20

    assert original["nested"]["value"] == 10