"""
Unit tests for foundation.utils.validation.

Python: 3.13+
"""

from __future__ import annotations

import uuid

import pytest

from foundation.exceptions import ValidationError
from foundation.utils.validation import (
    require_non_negative,
    require_not_empty,
    require_not_none,
    require_positive,
    require_unique,
    validate_event_name,
    validate_identifier,
    validate_semantic_version,
    validate_uuid,
)


# ============================================================================
# require_not_none
# ============================================================================


def test_require_not_none_accepts_valid_value() -> None:
    """A non-None value should pass validation."""
    require_not_none("value", "parameter")


def test_require_not_none_rejects_none() -> None:
    """None should raise ValidationError."""
    with pytest.raises(ValidationError):
        require_not_none(None, "parameter")


# ============================================================================
# require_not_empty
# ============================================================================


def test_require_not_empty_accepts_valid_string() -> None:
    """A non-empty string should pass validation."""
    require_not_empty("hello", "text")


@pytest.mark.parametrize("value", ["", " ", "\t", "\n"])
def test_require_not_empty_rejects_empty_strings(value: str) -> None:
    """Empty or whitespace-only strings should fail validation."""
    with pytest.raises(ValidationError):
        require_not_empty(value, "text")


# ============================================================================
# require_positive
# ============================================================================


def test_require_positive_accepts_positive_values() -> None:
    """Positive numbers should pass validation."""
    require_positive(1, "count")
    require_positive(1.5, "price")


@pytest.mark.parametrize("value", [0, -1, -100, -0.5])
def test_require_positive_rejects_invalid_values(
    value: int | float,
) -> None:
    """Zero and negative values should fail validation."""
    with pytest.raises(ValidationError):
        require_positive(value, "count")


# ============================================================================
# require_non_negative
# ============================================================================


def test_require_non_negative_accepts_zero_and_positive() -> None:
    """Zero and positive values should pass validation."""
    require_non_negative(0, "offset")
    require_non_negative(10, "offset")


@pytest.mark.parametrize("value", [-1, -10, -0.1])
def test_require_non_negative_rejects_negative_values(
    value: int | float,
) -> None:
    """Negative values should fail validation."""
    with pytest.raises(ValidationError):
        require_non_negative(value, "offset")


# ============================================================================
# validate_identifier
# ============================================================================


@pytest.mark.parametrize(
    "identifier",
    [
        "Plugin",
        "plugin_1",
        "ConfigManager",
        "BaseEvent",
    ],
)
def test_validate_identifier_accepts_valid_names(
    identifier: str,
) -> None:
    """Valid identifiers should pass validation."""
    assert validate_identifier(identifier)


@pytest.mark.parametrize(
    "identifier",
    [
        "",
        "123plugin",
        "plugin-name",
        "plugin name",
        "@plugin",
    ],
)
def test_validate_identifier_rejects_invalid_names(
    identifier: str,
) -> None:
    """Invalid identifiers should raise ValidationError."""
    with pytest.raises(ValidationError):
        validate_identifier(identifier)


# ============================================================================
# validate_event_name
# ============================================================================


@pytest.mark.parametrize(
    "event_name",
    [
        "market.tick",
        "risk.approved",
        "execution.order.created",
        "analytics.snapshot.updated",
    ],
)
def test_validate_event_name_accepts_valid_names(
    event_name: str,
) -> None:
    """Canonical event names should pass validation."""
    assert validate_event_name(event_name)


@pytest.mark.parametrize(
    "event_name",
    [
        "Market.Tick",
        "market_tick",
        "market",
        "market..tick",
        "",
    ],
)
def test_validate_event_name_rejects_invalid_names(
    event_name: str,
) -> None:
    """Invalid event names should raise ValidationError."""
    with pytest.raises(ValidationError):
        validate_event_name(event_name)


# ============================================================================
# validate_uuid
# ============================================================================


def test_validate_uuid_accepts_valid_uuid() -> None:
    """A valid UUID should pass validation."""
    value = str(uuid.uuid4())

    assert validate_uuid(value)


def test_validate_uuid_rejects_invalid_uuid() -> None:
    """Invalid UUIDs should raise ValidationError."""
    with pytest.raises(ValidationError):
        validate_uuid("not-a-uuid")


# ============================================================================
# validate_semantic_version
# ============================================================================


@pytest.mark.parametrize(
    "version",
    [
        "1.0.0",
        "0.1.0",
        "2.5.10",
        "1.2.3-alpha",
        "1.2.3+001",
        "1.2.3-beta+20260701",
    ],
)
def test_validate_semantic_version_accepts_valid_versions(
    version: str,
) -> None:
    """Valid semantic versions should pass validation."""
    assert validate_semantic_version(version)


@pytest.mark.parametrize(
    "version",
    [
        "",
        "1",
        "1.0",
        "v1.0.0",
        "1.0.x",
        "latest",
    ],
)
def test_validate_semantic_version_rejects_invalid_versions(
    version: str,
) -> None:
    """Invalid semantic versions should raise ValidationError."""
    with pytest.raises(ValidationError):
        validate_semantic_version(version)


# ============================================================================
# require_unique
# ============================================================================


def test_require_unique_accepts_unique_values() -> None:
    """Unique collections should pass validation."""
    require_unique([1, 2, 3], "numbers")


def test_require_unique_rejects_duplicates() -> None:
    """Duplicate values should raise ValidationError."""
    with pytest.raises(ValidationError):
        require_unique([1, 2, 2, 3], "numbers")