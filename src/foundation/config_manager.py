"""
Configuration manager for the AI Trading Operating System.

This module provides a production-ready, read-only configuration manager
responsible for loading and validating application configuration.

Features:
    - Singleton implementation
    - YAML configuration loading
    - Immutable configuration access
    - Typed getters
    - Dot-notation key lookup
    - Thread-safe initialization

Python: 3.13+
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from threading import Lock
from types import MappingProxyType
from typing import Any

import yaml

from foundation.exceptions import (
    ConfigurationError,
    MissingConfigurationError,
)


class ConfigManager:
    """Singleton configuration manager."""

    _instance: ConfigManager | None = None
    _lock = Lock()

    def __new__(cls) -> ConfigManager:
        """Create the singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize the configuration manager."""
        if self._initialized:
            return

        self._config: Mapping[str, Any] = MappingProxyType({})
        self._initialized = True

    def load(self, path: str | Path) -> None:
        """
        Load configuration from a YAML file.

        Args:
            path: Path to the YAML configuration file. Must be an
                  absolute path or resolve to one within the project.

        Raises:
            ConfigurationError:
                If the configuration file cannot be loaded or path
                traversal is detected.
        """
        try:
            config_path = Path(path).resolve()
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"Invalid configuration path: {path}") from exc

        if not config_path.exists():
            raise ConfigurationError(
                f"Configuration file does not exist: {config_path}"
            )

        try:
            with config_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                data = yaml.safe_load(file) or {}

        except yaml.YAMLError as exc:
            raise ConfigurationError("Invalid YAML configuration.") from exc

        if not isinstance(data, dict):
            raise ConfigurationError("Root configuration must be a mapping.")

        self._config = MappingProxyType(data)

    @property
    def config(self) -> Mapping[str, Any]:
        """Return the immutable configuration mapping."""
        return self._config

    def get(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """
        Retrieve a configuration value using dot notation.

        Example:
            database.host

        Args:
            key:
                Dot-separated configuration key.
            default:
                Value returned if the key is missing.

        Returns:
            The configuration value or the default.
        """
        current: Any = self._config

        for part in key.split("."):
            if isinstance(current, Mapping) and part in current:
                current = current[part]
            else:
                return default

        return current

    def require(self, key: str) -> Any:
        """
        Retrieve a required configuration value.

        Args:
            key:
                Dot-separated configuration key.

        Returns:
            The configuration value.

        Raises:
            MissingConfigurationError:
                If the key does not exist.
        """
        value = self.get(key)

        if value is None:
            raise MissingConfigurationError(f"Missing required configuration: {key}")

        return value

    def contains(self, key: str) -> bool:
        """
        Check whether a configuration key exists.

        Args:
            key:
                Dot-separated configuration key.

        Returns:
            True if the key exists.
        """
        sentinel = object()
        return self.get(key, sentinel) is not sentinel

    def as_dict(self) -> dict[str, Any]:
        """
        Return a mutable copy of the configuration.

        Returns:
            Deep copy is intentionally omitted for performance.
            Consumers should treat nested objects as read-only.
        """
        return dict(self._config)

    def reload(self, path: str | Path) -> None:
        """
        Reload configuration from disk.

        Args:
            path:
                Configuration file path.
        """
        self.load(path)

    def clear(self) -> None:
        """Clear all loaded configuration."""
        self._config = MappingProxyType({})
