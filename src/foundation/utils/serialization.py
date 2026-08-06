"""
Serialization utilities for the AI Trading Operating System.

This module provides deterministic JSON serialization and
deserialization helpers for immutable Foundation models.

Features:
    - UTF-8 JSON serialization
    - Deterministic output
    - Dataclass support
    - datetime support
    - UUID support
    - Path support
    - Pretty-print option
    - Framework-specific exceptions

Python: 3.13+
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from foundation.exceptions import (
    DeserializationError,
    SerializationError,
)


class _FoundationJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for Foundation objects."""

    def default(self, obj: Any) -> Any:
        """Serialize unsupported Python objects."""

        if is_dataclass(obj):
            return asdict(obj)

        if isinstance(obj, (datetime, date)):
            return obj.isoformat()

        if isinstance(obj, UUID):
            return str(obj)

        if isinstance(obj, Path):
            return str(obj)

        return super().default(obj)


def to_json(
    obj: Any,
    *,
    indent: int | None = None,
    sort_keys: bool = True,
) -> str:
    """Serialize an object to a JSON string.

    Args:
        obj:
            Object to serialize.
        indent:
            Optional indentation level.
        sort_keys:
            Whether to sort dictionary keys.

    Returns:
        JSON string.

    Raises:
        SerializationError:
            If serialization fails.
    """
    try:
        return json.dumps(
            obj,
            cls=_FoundationJSONEncoder,
            ensure_ascii=False,
            indent=indent,
            sort_keys=sort_keys,
        )
    except (TypeError, ValueError) as exc:
        raise SerializationError("Failed to serialize object to JSON.") from exc


def from_json(json_string: str) -> dict[str, Any]:
    """Deserialize a JSON string into a dictionary.

    Args:
        json_string:
            JSON string.

    Returns:
        Parsed dictionary.

    Raises:
        DeserializationError:
            If the JSON is invalid.
    """
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as exc:
        raise DeserializationError("Invalid JSON.") from exc

    if not isinstance(data, dict):
        raise DeserializationError("Top-level JSON object must be a dictionary.")

    return data


def write_json(
    path: str | Path,
    obj: Any,
    *,
    indent: int = 4,
) -> None:
    """Write an object as JSON to disk.

    Args:
        path:
            Destination file.
        obj:
            Object to serialize.
        indent:
            Pretty-print indentation.

    Raises:
        SerializationError:
            If writing fails.
    """
    file_path = Path(path).resolve()

    try:
        file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        file_path.write_text(
            to_json(
                obj,
                indent=indent,
            ),
            encoding="utf-8",
        )

    except OSError as exc:
        raise SerializationError(f"Unable to write JSON file: {file_path}") from exc


def read_json(path: str | Path) -> dict[str, Any]:
    """Read a JSON file.

    Args:
        path:
            JSON file path.

    Returns:
        Parsed dictionary.

    Raises:
        DeserializationError:
            If reading or parsing fails.
    """
    file_path = Path(path).resolve()

    try:
        content = file_path.read_text(
            encoding="utf-8",
        )
    except OSError as exc:
        raise DeserializationError(f"Unable to read JSON file: {file_path}") from exc

    return from_json(content)


def clone(obj: Any) -> Any:
    """Create a deep JSON-compatible copy of an object.

    Args:
        obj:
            Object to clone.

    Returns:
        Deep copy of the object.

    Raises:
        SerializationError:
            If cloning fails.
    """
    return json.loads(to_json(obj))
