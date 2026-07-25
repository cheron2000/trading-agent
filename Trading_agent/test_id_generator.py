"""
Unit tests for foundation.utils.id_generator.

Python: 3.13+
"""

from __future__ import annotations

import re
import uuid

from foundation.utils.id_generator import (
    generate_correlation_id,
    generate_event_id,
    generate_plugin_id,
    generate_request_id,
    generate_session_id,
    generate_trace_id,
    generate_uuid,
)


UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-"
    r"[0-9a-f]{4}-"
    r"[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-"
    r"[0-9a-f]{12}$"
)


# ============================================================================
# UUID Generation
# ============================================================================


def test_generate_uuid_returns_valid_uuid() -> None:
    """generate_uuid() should return a valid UUID string."""
    value = generate_uuid()

    assert UUID_PATTERN.match(value)
    assert str(uuid.UUID(value)) == value


def test_generate_uuid_is_unique() -> None:
    """Generated UUIDs should be unique."""
    first = generate_uuid()
    second = generate_uuid()

    assert first != second


# ============================================================================
# Event ID
# ============================================================================


def test_generate_event_id_returns_valid_uuid() -> None:
    """Event IDs should be valid UUIDs."""
    value = generate_event_id()

    assert UUID_PATTERN.match(value)


# ============================================================================
# Correlation ID
# ============================================================================


def test_generate_correlation_id_returns_valid_uuid() -> None:
    """Correlation IDs should be valid UUIDs."""
    value = generate_correlation_id()

    assert UUID_PATTERN.match(value)


# ============================================================================
# Trace ID
# ============================================================================


def test_generate_trace_id_returns_valid_uuid() -> None:
    """Trace IDs should be valid UUIDs."""
    value = generate_trace_id()

    assert UUID_PATTERN.match(value)


# ============================================================================
# Session ID
# ============================================================================


def test_generate_session_id_returns_valid_uuid() -> None:
    """Session IDs should be valid UUIDs."""
    value = generate_session_id()

    assert UUID_PATTERN.match(value)


# ============================================================================
# Request ID
# ============================================================================


def test_generate_request_id_returns_valid_uuid() -> None:
    """Request IDs should be valid UUIDs."""
    value = generate_request_id()

    assert UUID_PATTERN.match(value)


# ============================================================================
# Plugin ID
# ============================================================================


def test_generate_plugin_id_returns_valid_uuid() -> None:
    """Plugin IDs should be valid UUIDs."""
    value = generate_plugin_id()

    assert UUID_PATTERN.match(value)


# ============================================================================
# Uniqueness
# ============================================================================


def test_all_generated_ids_are_unique() -> None:
    """Each generated ID should be unique."""
    ids = {
        generate_uuid(),
        generate_event_id(),
        generate_correlation_id(),
        generate_trace_id(),
        generate_session_id(),
        generate_request_id(),
        generate_plugin_id(),
    }

    assert len(ids) == 7


def test_generated_ids_are_valid_uuid_objects() -> None:
    """Generated IDs should be parseable as UUID objects."""
    generators = (
        generate_uuid,
        generate_event_id,
        generate_correlation_id,
        generate_trace_id,
        generate_session_id,
        generate_request_id,
        generate_plugin_id,
    )

    for generator in generators:
        value = generator()
        parsed = uuid.UUID(value)

        assert str(parsed) == value