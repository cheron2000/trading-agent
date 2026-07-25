"""
ID generation utilities for the AI Trading Operating System.

This module provides standardized identifier generation and validation
functions used throughout the Foundation Layer.

Features:
    - UUID4 generation
    - UUID validation
    - Short identifier generation
    - Batch identifier generation

Python: 3.13+
"""

from __future__ import annotations

import secrets
from uuid import UUID, uuid4

from foundation.exceptions import ValidationError


def generate_uuid() -> str:
    """Generate a random UUID (version 4).

    Returns:
        A UUID4 string.
    """
    return str(uuid4())


def generate_short_id(length: int = 12) -> str:
    """Generate a cryptographically secure short identifier.

    The identifier consists only of lowercase hexadecimal characters.

    Args:
        length:
            Desired identifier length.

    Returns:
        A secure random identifier.

    Raises:
        ValueError:
            If length is less than 1.
    """
    if length < 1:
        raise ValueError("length must be greater than zero.")

    while True:
        identifier = secrets.token_hex((length + 1) // 2)[:length]

        if len(identifier) == length:
            return identifier


def generate_many(count: int) -> tuple[str, ...]:
    """Generate multiple UUID4 identifiers.

    Args:
        count:
            Number of identifiers to generate.

    Returns:
        Tuple of UUID strings.

    Raises:
        ValueError:
            If count is less than 1.
    """
    if count < 1:
        raise ValueError("count must be greater than zero.")

    return tuple(generate_uuid() for _ in range(count))


def is_valid_uuid(value: str) -> bool:
    """Determine whether a string is a valid UUID.

    Args:
        value:
            UUID string.

    Returns:
        True if valid, otherwise False.
    """
    try:
        UUID(value)
        return True
    except (ValueError, TypeError):
        return False


def require_valid_uuid(value: str) -> None:
    """Validate that a UUID is well-formed.

    Args:
        value:
            UUID string.

    Raises:
        ValidationError:
            If the UUID is invalid.
    """
    if not is_valid_uuid(value):
        raise ValidationError(
            f"Invalid UUID: '{value}'."
        )


def normalize_uuid(value: str) -> str:
    """Normalize a UUID string.

    Args:
        value:
            UUID string.

    Returns:
        Canonical lowercase UUID string.

    Raises:
        ValidationError:
            If the UUID is invalid.
    """
    try:
        return str(UUID(value))
    except (ValueError, TypeError) as exc:
        raise ValidationError(
            f"Invalid UUID: '{value}'."
        ) from exc


def generate_prefixed_id(prefix: str) -> str:
    """Generate a prefixed identifier.

    Example:
        plugin_550e8400-e29b-41d4-a716-446655440000

    Args:
        prefix:
            Identifier prefix.

    Returns:
        Prefixed identifier.

    Raises:
        ValueError:
            If prefix is empty.
    """
    if not prefix.strip():
        raise ValueError("prefix must not be empty.")

    return f"{prefix}_{generate_uuid()}"