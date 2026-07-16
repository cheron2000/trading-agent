"""
communication.models.plugin_manifest
===================================

Defines the immutable plugin manifest used by the Communication Layer.

A PluginManifest describes a plugin's metadata, declared capabilities,
dependencies, and communication contract. It is purely declarative and
contains no plugin loading, discovery, or lifecycle logic.

The manifest is intentionally transport-independent and suitable for
deterministic serialization.

Python Version:
    3.13+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class PluginManifest:
    """Immutable plugin manifest.

    Attributes:
        plugin_id:
            Globally unique identifier for the plugin.

        name:
            Human-readable plugin name.

        version:
            Semantic version of the plugin.

        description:
            Short description of the plugin.

        author:
            Plugin author or organization.

        api_version:
            Required Communication/Foundation API version.

        entry_point:
            Fully-qualified Python import path to the plugin entry point.

        dependencies:
            Required plugin identifiers.

        optional_dependencies:
            Optional plugin identifiers.

        capabilities:
            Declared capabilities provided by the plugin.

        event_subscriptions:
            Canonical event patterns consumed by the plugin.

        event_publications:
            Canonical event names published by the plugin.

        tags:
            Classification labels.

        configuration_schema:
            Optional schema identifier or reference used for
            configuration validation.
    """

    plugin_id: str
    name: str
    version: str
    description: str
    author: str
    api_version: str
    entry_point: str

    dependencies: tuple[str, ...] = field(default_factory=tuple)
    optional_dependencies: tuple[str, ...] = field(default_factory=tuple)

    capabilities: tuple[str, ...] = field(default_factory=tuple)

    event_subscriptions: tuple[str, ...] = field(default_factory=tuple)
    event_publications: tuple[str, ...] = field(default_factory=tuple)

    tags: tuple[str, ...] = field(default_factory=tuple)

    configuration_schema: str | None = None

    _MAX_TEXT_LENGTH: ClassVar[int] = 255
    _MAX_DESCRIPTION_LENGTH: ClassVar[int] = 2048

    def __post_init__(self) -> None:
        """Validate manifest fields.

        Raises:
            ValueError:
                If one or more fields contain invalid values.
        """
        self._validate_required("plugin_id", self.plugin_id)
        self._validate_required("name", self.name)
        self._validate_required("version", self.version)
        self._validate_required("author", self.author)
        self._validate_required("api_version", self.api_version)
        self._validate_required("entry_point", self.entry_point)

        if not self.description.strip():
            raise ValueError("description must not be empty.")

        if len(self.description) > self._MAX_DESCRIPTION_LENGTH:
            raise ValueError(
                "description exceeds maximum length."
            )

        self._validate_collection(
            "dependencies",
            self.dependencies,
        )

        self._validate_collection(
            "optional_dependencies",
            self.optional_dependencies,
        )

        self._validate_collection(
            "capabilities",
            self.capabilities,
        )

        self._validate_collection(
            "event_subscriptions",
            self.event_subscriptions,
        )

        self._validate_collection(
            "event_publications",
            self.event_publications,
        )

        self._validate_collection(
            "tags",
            self.tags,
        )

        if (
            self.configuration_schema is not None
            and not self.configuration_schema.strip()
        ):
            raise ValueError(
                "configuration_schema cannot be empty."
            )

    @classmethod
    def _validate_required(
        cls,
        field_name: str,
        value: str,
    ) -> None:
        """Validate a required string field."""
        if not value.strip():
            raise ValueError(f"{field_name} must not be empty.")

        if len(value) > cls._MAX_TEXT_LENGTH:
            raise ValueError(
                f"{field_name} exceeds maximum length."
            )

    @staticmethod
    def _validate_collection(
        field_name: str,
        values: tuple[str, ...],
    ) -> None:
        """Validate an immutable string collection."""
        if len(values) != len(set(values)):
            raise ValueError(
                f"{field_name} contains duplicate values."
            )

        for item in values:
            if not item.strip():
                raise ValueError(
                    f"{field_name} contains an empty value."
                )

    @property
    def has_dependencies(self) -> bool:
        """Return whether the plugin declares dependencies."""
        return bool(self.dependencies)

    @property
    def publishes_events(self) -> bool:
        """Return whether the plugin publishes events."""
        return bool(self.event_publications)

    @property
    def subscribes_to_events(self) -> bool:
        """Return whether the plugin subscribes to events."""
        return bool(self.event_subscriptions)

    def to_dict(self) -> dict[str, object]:
        """Serialize the manifest deterministically.

        Returns:
            Dictionary suitable for JSON serialization.
        """
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "api_version": self.api_version,
            "entry_point": self.entry_point,
            "dependencies": list(self.dependencies),
            "optional_dependencies": list(
                self.optional_dependencies
            ),
            "capabilities": list(self.capabilities),
            "event_subscriptions": list(
                self.event_subscriptions
            ),
            "event_publications": list(
                self.event_publications
            ),
            "tags": list(self.tags),
            "configuration_schema": (
                self.configuration_schema
            ),
        }

    def __str__(self) -> str:
        """Return a concise human-readable representation."""
        return (
            "PluginManifest("
            f"id='{self.plugin_id}', "
            f"name='{self.name}', "
            f"version='{self.version}')"
        )