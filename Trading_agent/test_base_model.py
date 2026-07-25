"""
Unit tests for foundation.models.base_model.

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest

from foundation.models.base_model import BaseModel


@dataclass(frozen=True, slots=True, kw_only=True)
class SampleModel(BaseModel):
    """Concrete model used for testing."""

    name: str
    value: int


# ============================================================================
# Construction
# ============================================================================


def test_model_creation() -> None:
    """A model should be created successfully."""
    model = SampleModel(
        name="example",
        value=100,
    )

    assert model.name == "example"
    assert model.value == 100


def test_model_generates_uuid() -> None:
    """A UUID should be generated automatically."""
    model = SampleModel(
        name="example",
        value=1,
    )

    uuid = UUID(model.id)

    assert str(uuid) == model.id


def test_model_created_at_is_utc() -> None:
    """created_at should be timezone-aware UTC."""
    model = SampleModel(
        name="example",
        value=1,
    )

    assert isinstance(model.created_at, datetime)
    assert model.created_at.tzinfo == UTC


# ============================================================================
# Immutability
# ============================================================================


def test_model_is_immutable() -> None:
    """BaseModel should be immutable."""
    model = SampleModel(
        name="example",
        value=1,
    )

    with pytest.raises(FrozenInstanceError):
        model.name = "changed"  # type: ignore[misc]


# ============================================================================
# Serialization
# ============================================================================


def test_to_dict() -> None:
    """Model should serialize to a dictionary."""
    model = SampleModel(
        name="example",
        value=42,
    )

    data = model.to_dict()

    assert data["id"] == model.id
    assert data["name"] == "example"
    assert data["value"] == 42
    assert "created_at" in data


def test_to_json_returns_dictionary() -> None:
    """to_json() should return a JSON-compatible dictionary."""
    model = SampleModel(
        name="example",
        value=10,
    )

    data = model.to_json()

    assert isinstance(data, dict)
    assert data["name"] == "example"


def test_from_dict() -> None:
    """Model should be reconstructed from a dictionary."""
    original = SampleModel(
        name="example",
        value=5,
    )

    restored = SampleModel.from_dict(original.to_dict())

    assert restored == original


# ============================================================================
# Representation
# ============================================================================


def test_str_representation() -> None:
    """__str__ should contain the class name and ID."""
    model = SampleModel(
        name="example",
        value=1,
    )

    text = str(model)

    assert "SampleModel" in text
    assert model.id in text


def test_repr_representation() -> None:
    """__repr__ should contain identifying information."""
    model = SampleModel(
        name="example",
        value=1,
    )

    text = repr(model)

    assert "SampleModel" in text
    assert model.id in text


# ============================================================================
# Equality
# ============================================================================


def test_models_with_same_data_are_equal() -> None:
    """Dataclass equality should work correctly."""
    model = SampleModel(
        name="example",
        value=10,
    )

    restored = SampleModel.from_dict(model.to_dict())

    assert model == restored


def test_models_have_unique_ids() -> None:
    """Different instances should receive unique IDs."""
    model1 = SampleModel(
        name="a",
        value=1,
    )

    model2 = SampleModel(
        name="a",
        value=1,
    )

    assert model1.id != model2.id