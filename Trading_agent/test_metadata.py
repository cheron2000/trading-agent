"""
Unit tests for foundation.models.metadata.

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

from foundation.models.metadata import Metadata


# ============================================================================
# Construction
# ============================================================================


def test_metadata_creation() -> None:
    """Metadata should be created successfully."""
    metadata = Metadata(
        name="Market Data",
        description="Provider metadata",
        owner="orion",
        tags=("market", "provider"),
        attributes={
            "exchange": "NASDAQ",
            "region": "US",
        },
    )

    assert metadata.name == "Market Data"
    assert metadata.description == "Provider metadata"
    assert metadata.owner == "orion"
    assert metadata.tags == ("market", "provider")
    assert metadata.attributes["exchange"] == "NASDAQ"
    assert metadata.attributes["region"] == "US"


def test_default_values() -> None:
    """Optional fields should have sensible defaults."""
    metadata = Metadata(name="Example")

    assert metadata.description is None
    assert metadata.owner is None
    assert metadata.tags == ()
    assert len(metadata.attributes) == 0


# ============================================================================
# Immutability
# ============================================================================


def test_metadata_is_immutable() -> None:
    """Metadata should be immutable."""
    metadata = Metadata(name="Example")

    with pytest.raises(FrozenInstanceError):
        metadata.name = "Changed"  # type: ignore[misc]


def test_attributes_are_mapping_proxy() -> None:
    """Attributes should be exposed as a read-only mapping."""
    metadata = Metadata(
        name="Example",
        attributes={"key": "value"},
    )

    assert isinstance(metadata.attributes, MappingProxyType)

    with pytest.raises(TypeError):
        metadata.attributes["new"] = "item"  # type: ignore[index]


# ============================================================================
# Helper Properties
# ============================================================================


def test_has_tags_property() -> None:
    """has_tags should reflect whether tags exist."""
    assert Metadata(name="A").has_tags is False
    assert Metadata(name="B", tags=("one",)).has_tags is True


def test_has_attributes_property() -> None:
    """has_attributes should reflect whether attributes exist."""
    assert Metadata(name="A").has_attributes is False

    metadata = Metadata(
        name="B",
        attributes={"k": "v"},
    )

    assert metadata.has_attributes is True


# ============================================================================
# Tag Helpers
# ============================================================================


def test_contains_tag() -> None:
    """contains_tag should detect existing tags."""
    metadata = Metadata(
        name="Example",
        tags=("risk", "ai"),
    )

    assert metadata.contains_tag("risk")
    assert not metadata.contains_tag("market")


def test_with_tag_returns_new_instance() -> None:
    """with_tag should return a new immutable instance."""
    original = Metadata(name="Example")
    updated = original.with_tag("analytics")

    assert original is not updated
    assert original.tags == ()
    assert updated.tags == ("analytics",)


def test_with_tag_ignores_duplicates() -> None:
    """Adding an existing tag should return the same instance."""
    metadata = Metadata(
        name="Example",
        tags=("core",),
    )

    assert metadata.with_tag("core") is metadata


# ============================================================================
# Attribute Helpers
# ============================================================================


def test_get_attribute_existing() -> None:
    """Existing attributes should be returned."""
    metadata = Metadata(
        name="Example",
        attributes={"region": "EU"},
    )

    assert metadata.get_attribute("region") == "EU"


def test_get_attribute_default() -> None:
    """Missing attributes should return the supplied default."""
    metadata = Metadata(name="Example")

    assert metadata.get_attribute("missing", "default") == "default"


def test_with_attribute_returns_new_instance() -> None:
    """with_attribute should return a modified copy."""
    original = Metadata(name="Example")
    updated = original.with_attribute("source", "polygon")

    assert original is not updated
    assert not original.has_attributes
    assert updated.attributes["source"] == "polygon"


# ============================================================================
# BaseModel Inheritance
# ============================================================================


def test_metadata_has_identifier() -> None:
    """Metadata should inherit BaseModel fields."""
    metadata = Metadata(name="Example")

    assert metadata.id
    assert metadata.created_at is not None