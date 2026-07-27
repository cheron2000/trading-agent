"""
Immutable metadata model for the AI Trading Operating System.

This module defines the canonical metadata object shared across the
Foundation Layer. Metadata provides standardized audit and tracing
information for immutable models without introducing domain-specific
behavior.

Python: 3.13+
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from foundation.models.base_model import BaseModel


@dataclass(frozen=True, slots=True, kw_only=True)
class Metadata(BaseModel):
    """Immutable metadata model.

    This model contains common metadata used for auditing,
    traceability, ownership, and tagging.

    Attributes:
        name:
            Human-readable object name.
        description:
            Optional description.
        owner:
            Component or plugin that created the object.
        tags:
            Immutable collection of tags.
        attributes:
            Immutable key-value metadata.
    """

    name: str
    description: str | None = None
    owner: str | None = None
    tags: tuple[str, ...] = ()
    attributes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize immutable collections."""

        object.__setattr__(self, "tags", tuple(self.tags))

        object.__setattr__(
            self,
            "attributes",
            MappingProxyType(dict(self.attributes)),
        )

    @property
    def has_tags(self) -> bool:
        """Return True if one or more tags are present."""
        return bool(self.tags)

    @property
    def has_attributes(self) -> bool:
        """Return True if custom attributes exist."""
        return bool(self.attributes)

    def contains_tag(self, tag: str) -> bool:
        """Determine whether a tag exists.

        Args:
            tag:
                Tag to search for.

        Returns:
            True if the tag exists.
        """
        return tag in self.tags

    def get_attribute(
        self,
        key: str,
        default: str | None = None,
    ) -> str | None:
        """Retrieve an attribute value.

        Args:
            key:
                Attribute name.
            default:
                Returned if the attribute does not exist.

        Returns:
            Attribute value or default.
        """
        return self.attributes.get(key, default)

    def with_attribute(
        self,
        key: str,
        value: str,
    ) -> Metadata:
        """Return a new Metadata instance with an added attribute.

        The original instance remains unchanged.

        Args:
            key:
                Attribute key.
            value:
                Attribute value.

        Returns:
            A new immutable Metadata instance.
        """
        updated = dict(self.attributes)
        updated[key] = value

        return Metadata(
            id=self.id,
            created_at=self.created_at,
            name=self.name,
            description=self.description,
            owner=self.owner,
            tags=self.tags,
            attributes=updated,
        )

    def with_tag(self, tag: str) -> Metadata:
        """Return a new Metadata instance with an added tag.

        Duplicate tags are ignored.

        Args:
            tag:
                Tag to add.

        Returns:
            A new immutable Metadata instance.
        """
        if tag in self.tags:
            return self

        return Metadata(
            id=self.id,
            created_at=self.created_at,
            name=self.name,
            description=self.description,
            owner=self.owner,
            tags=(*self.tags, tag),
            attributes=self.attributes,
        )
