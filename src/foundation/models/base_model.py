"""
Immutable base model for the AI Trading Operating System.

This module defines the common immutable model that all shared data models
should inherit from. It provides a consistent identity, creation timestamp,
serialization support, and value-based equality.

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True, kw_only=True)
class BaseModel:
    """Base class for immutable shared models.

    Every shared model inherits a globally unique identifier and a UTC
    creation timestamp. The model is immutable to guarantee thread safety
    and predictable behavior throughout the system.

    Attributes:
        id:
            Globally unique identifier.
        created_at:
            UTC timestamp indicating when the model was created.
    """

    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert the model into a dictionary.

        Returns:
            Dictionary representation of the model.
        """
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data

    def to_json(self) -> dict[str, Any]:
        """Return a JSON-serializable representation.

        Returns:
            JSON-compatible dictionary.
        """
        return self.to_dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseModel":
        """Create an instance from a dictionary.

        Args:
            data:
                Dictionary containing model values.

        Returns:
            A new model instance.
        """
        payload = dict(data)

        if "created_at" in payload:
            payload["created_at"] = datetime.fromisoformat(
                payload["created_at"]
            )

        return cls(**payload)

    def __str__(self) -> str:
        """Return a human-readable representation."""
        return (
            f"{self.__class__.__name__}"
            f"(id='{self.id}')"
        )

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self.id}', "
            f"created_at='{self.created_at.isoformat()}')"
        )