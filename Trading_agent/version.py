"""
Immutable semantic version model.

This module defines the canonical semantic version representation used
throughout the AI Trading Operating System.

The model follows Semantic Versioning (SemVer 2.0.0):
https://semver.org/

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from foundation.models.base_model import BaseModel

_SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z.-]+))?"
    r"(?:\+([0-9A-Za-z.-]+))?$"
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Version(BaseModel):
    """Immutable semantic version.

    Attributes:
        major:
            Major version number.
        minor:
            Minor version number.
        patch:
            Patch version number.
        prerelease:
            Optional prerelease identifier.
        build:
            Optional build metadata.
    """

    major: int
    minor: int
    patch: int
    prerelease: str | None = None
    build: str | None = None

    def __post_init__(self) -> None:
        """Validate semantic version values."""
        if self.major < 0:
            raise ValueError("major version must be >= 0")

        if self.minor < 0:
            raise ValueError("minor version must be >= 0")

        if self.patch < 0:
            raise ValueError("patch version must be >= 0")

    @classmethod
    def parse(cls, value: str) -> "Version":
        """Parse a semantic version string.

        Args:
            value:
                Semantic version string.

        Returns:
            Parsed Version instance.

        Raises:
            ValueError:
                If the version string is invalid.
        """
        match = _SEMVER_PATTERN.fullmatch(value)

        if match is None:
            raise ValueError(f"Invalid semantic version: {value}")

        major, minor, patch, prerelease, build = match.groups()

        return cls(
            major=int(major),
            minor=int(minor),
            patch=int(patch),
            prerelease=prerelease,
            build=build,
        )

    def __str__(self) -> str:
        """Return semantic version string."""
        version = f"{self.major}.{self.minor}.{self.patch}"

        if self.prerelease:
            version += f"-{self.prerelease}"

        if self.build:
            version += f"+{self.build}"

        return version

    def __lt__(self, other: object) -> bool:
        """Compare semantic versions.

        Prerelease precedence is intentionally not implemented.
        This comparison considers only major, minor, and patch.
        """
        if not isinstance(other, Version):
            return NotImplemented

        return (
            self.major,
            self.minor,
            self.patch,
        ) < (
            other.major,
            other.minor,
            other.patch,
        )

    def __le__(self, other: object) -> bool:
        """Return self <= other."""
        result = self.__lt__(other)
        if result is NotImplemented:
            return NotImplemented
        return result or self == other

    def __gt__(self, other: object) -> bool:
        """Return self > other."""
        if not isinstance(other, Version):
            return NotImplemented
        return other < self

    def __ge__(self, other: object) -> bool:
        """Return self >= other."""
        if not isinstance(other, Version):
            return NotImplemented
        return not self < other