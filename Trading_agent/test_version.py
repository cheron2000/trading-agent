"""
Unit tests for foundation.models.version.

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from foundation.exceptions import ValidationError
from foundation.models.version import Version


# ============================================================================
# Construction
# ============================================================================


def test_version_creation() -> None:
    """A Version object should be created successfully."""
    version = Version(
        major=1,
        minor=2,
        patch=3,
    )

    assert version.major == 1
    assert version.minor == 2
    assert version.patch == 3


def test_default_prerelease_and_build() -> None:
    """Prerelease and build metadata should default to None."""
    version = Version(
        major=1,
        minor=0,
        patch=0,
    )

    assert version.prerelease is None
    assert version.build_metadata is None


# ============================================================================
# String Representation
# ============================================================================


def test_string_representation() -> None:
    """Version should format as semantic version."""
    version = Version(
        major=1,
        minor=2,
        patch=3,
    )

    assert str(version) == "1.2.3"


def test_prerelease_representation() -> None:
    """Prerelease should be included in the version string."""
    version = Version(
        major=1,
        minor=2,
        patch=3,
        prerelease="rc1",
    )

    assert str(version) == "1.2.3-rc1"


def test_build_metadata_representation() -> None:
    """Build metadata should be appended correctly."""
    version = Version(
        major=1,
        minor=2,
        patch=3,
        build_metadata="build7",
    )

    assert str(version) == "1.2.3+build7"


def test_full_semantic_version_representation() -> None:
    """Prerelease and build metadata should both be represented."""
    version = Version(
        major=1,
        minor=2,
        patch=3,
        prerelease="beta",
        build_metadata="20260701",
    )

    assert str(version) == "1.2.3-beta+20260701"


# ============================================================================
# Parsing
# ============================================================================


def test_parse_semantic_version() -> None:
    """A semantic version string should be parsed successfully."""
    version = Version.parse("2.5.9")

    assert version.major == 2
    assert version.minor == 5
    assert version.patch == 9


def test_parse_full_semantic_version() -> None:
    """Prerelease and build metadata should be parsed."""
    version = Version.parse("1.0.0-alpha+001")

    assert version.prerelease == "alpha"
    assert version.build_metadata == "001"


def test_invalid_semantic_version() -> None:
    """Invalid semantic versions should raise ValidationError."""
    with pytest.raises(ValidationError):
        Version.parse("invalid")


# ============================================================================
# Comparison
# ============================================================================


def test_version_equality() -> None:
    """Equal versions should compare equal."""
    assert Version.parse("1.2.3") == Version.parse("1.2.3")


def test_version_less_than() -> None:
    """Version ordering should work."""
    assert Version.parse("1.2.3") < Version.parse("1.2.4")


def test_version_greater_than() -> None:
    """Version ordering should work."""
    assert Version.parse("2.0.0") > Version.parse("1.9.9")


# ============================================================================
# Immutability
# ============================================================================


def test_version_is_immutable() -> None:
    """Version should be immutable."""
    version = Version.parse("1.0.0")

    with pytest.raises(FrozenInstanceError):
        version.major = 2  # type: ignore[misc]


# ============================================================================
# Validation
# ============================================================================


@pytest.mark.parametrize(
    "major,minor,patch",
    [
        (-1, 0, 0),
        (0, -1, 0),
        (0, 0, -1),
    ],
)
def test_negative_components_raise_validation_error(
    major: int,
    minor: int,
    patch: int,
) -> None:
    """Negative version components should not be accepted."""
    with pytest.raises(ValidationError):
        Version(
            major=major,
            minor=minor,
            patch=patch,
        )