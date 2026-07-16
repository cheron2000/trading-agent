"""
Validation utilities for the AI Trading Operating System.

This module provides reusable validation helpers shared across the
Foundation Layer. The functions are deterministic, side-effect free,
and raise framework-specific exceptions when validation fails.

Python: 3.13+
"""

from __future__ import annotations

import re
from collections.abc import Collection
from pathlib import Path
from typing import Any
from uuid import UUID

from foundation.exceptions import ValidationError

# ============================================================================
# Safe path resolution — prevents CWE-22 path traversal
# ============================================================================

def _safe_resolve(base: Path, user_path: str | Path) -> Path:
    """Resolve user_path relative to base, blocking traversal attempts.

    Args:
        base:      Trusted root directory.
        user_path: User-supplied path fragment.

    Returns:
        Resolved absolute Path guaranteed to be inside base.

    Raises:
        ValueError: If the resolved path escapes base.
    """
    resolved = (base / user_path).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise ValueError(
            f"Path traversal blocked: {user_path!r} escapes base {base!r}."
        )
    return resolved

# ============================================================================
# Regular Expressions
# ============================================================================

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")
_EVENT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}(?:\.[a-z0-9_]{1,63}){1,8}$")
_SEMVER_PATTERN = re.compile(
    r"^(?:0|[1-9]\d{0,9})\.(?:0|[1-9]\d{0,9})\.(?:0|[1-9]\d{0,9})"
    r"(?:-[0-9A-Za-z][0-9A-Za-z.\-]{0,127})?"
    r"(?:\+[0-9A-Za-z][0-9A-Za-z.\-]{0,127})?$"
)


def require_not_none(value: Any, name: str) -> None:
    """Ensure a value is not None.

    Args:
        value: Value to validate.
        name: Human-readable parameter name.

    Raises:
        ValidationError: If the value is None.
    """
    if value is None:
        raise ValidationError(f"'{name}' must not be None.")


def require_not_empty(value: str, name: str) -> None:
    """Ensure a string is not empty or whitespace.

    Args:
        value: String to validate.
        name: Parameter name.

    Raises:
        ValidationError: If the string is empty.
    """
    require_not_none(value, name)

    if not value.strip():
        raise ValidationError(f"'{name}' must not be empty.")


def require_positive(value: int | float, name: str) -> None:
    """Ensure a numeric value is greater than zero.

    Args:
        value: Numeric value.
        name: Parameter name.

    Raises:
        ValidationError: If the value is not positive.
    """
    if value <= 0:
        raise ValidationError(f"'{name}' must be greater than zero.")


def require_non_negative(value: int | float, name: str) -> None:
    """Ensure a numeric value is non-negative.

    Args:
        value: Numeric value.
        name: Parameter name.

    Raises:
        ValidationError: If the value is negative.
    """
    if value < 0:
        raise ValidationError(f"'{name}' must be non-negative.")


def validate_identifier(identifier: str) -> bool:
    """Validate a Python-style identifier.

    Args:
        identifier: Identifier to validate.

    Returns:
        True if valid.

    Raises:
        ValidationError: If the identifier is invalid.
    """
    require_not_empty(identifier, "identifier")

    if _IDENTIFIER_PATTERN.fullmatch(identifier) is None:
        raise ValidationError(
            f"Invalid identifier: '{identifier}'."
        )

    return True


def validate_event_name(event_name: str) -> bool:
    """Validate a canonical event name.

    Event names must follow dot notation, for example:
        market.tick
        risk.approved
        execution.order.created

    Args:
        event_name: Event name.

    Returns:
        True if valid.

    Raises:
        ValidationError: If invalid.
    """
    require_not_empty(event_name, "event_name")

    if _EVENT_NAME_PATTERN.fullmatch(event_name) is None:
        raise ValidationError(
            f"Invalid event name: '{event_name}'."
        )

    return True


def validate_uuid(value: str) -> bool:
    """Validate a UUID string.

    Args:
        value: UUID string.

    Returns:
        True if valid.

    Raises:
        ValidationError: If invalid.
    """
    require_not_empty(value, "uuid")

    try:
        UUID(value)
    except ValueError as exc:
        raise ValidationError(
            f"Invalid UUID: '{value}'."
        ) from exc

    return True


def validate_semantic_version(version: str) -> bool:
    """Validate a semantic version string.

    Args:
        version: Semantic version.

    Returns:
        True if valid.

    Raises:
        ValidationError: If invalid.
    """
    require_not_empty(version, "version")

    if _SEMVER_PATTERN.fullmatch(version) is None:
        raise ValidationError(
            f"Invalid semantic version: '{version}'."
        )

    return True


def validate_file_exists(path: str | Path) -> bool:
    """Validate that a file path exists and does not escape the working directory.

    Args:
        path: File path to validate.

    Returns:
        True if the file exists.

    Raises:
        ValidationError: If the file does not exist or path traversal is detected.
    """
    try:
        file_path = Path(path).resolve()
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Invalid file path: {path}") from exc

    if not file_path.is_file():
        raise ValidationError(
            f"File does not exist: {file_path}"
        )

    return True


def require_unique(values: Collection[Any], name: str) -> None:
    """Ensure all values in a collection are unique.

    Args:
        values: Collection to validate.
        name: Collection name.

    Raises:
        ValidationError: If duplicates are found.
    """
    if len(values) != len(set(values)):
        raise ValidationError(
            f"'{name}' contains duplicate values."
        )