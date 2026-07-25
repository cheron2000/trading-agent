"""
Unit tests for foundation.config_manager.

Python: 3.13+
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from foundation.config_manager import ConfigManager
from foundation.exceptions import (
    ConfigurationError,
    MissingConfigurationError,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def reset_config_manager() -> None:
    """Reset the singleton before each test."""
    manager = ConfigManager()
    manager.clear()
    yield
    manager.clear()


# ============================================================================
# Singleton
# ============================================================================


def test_singleton_instance() -> None:
    """ConfigManager should implement the singleton pattern."""
    manager1 = ConfigManager()
    manager2 = ConfigManager()

    assert manager1 is manager2


# ============================================================================
# Loading Configuration
# ============================================================================


def test_load_configuration(tmp_path: Path) -> None:
    """Configuration should load successfully."""
    config_file = tmp_path / "config.yaml"

    yaml.safe_dump(
        {
            "app": {
                "name": "AITOS",
                "version": "1.0.0",
            }
        },
        config_file.open("w", encoding="utf-8"),
    )

    manager = ConfigManager()
    manager.load(config_file)

    assert manager.get("app.name") == "AITOS"
    assert manager.get("app.version") == "1.0.0"


def test_missing_configuration_file() -> None:
    """Loading a missing configuration should fail."""
    manager = ConfigManager()

    with pytest.raises(ConfigurationError):
        manager.load("does_not_exist.yaml")


def test_invalid_yaml(tmp_path: Path) -> None:
    """Invalid YAML should raise ConfigurationError."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("::: invalid :::", encoding="utf-8")

    manager = ConfigManager()

    with pytest.raises(ConfigurationError):
        manager.load(config_file)


# ============================================================================
# Getters
# ============================================================================


def test_get_existing_key(tmp_path: Path) -> None:
    """Existing configuration values should be returned."""
    config_file = tmp_path / "config.yaml"

    yaml.safe_dump(
        {"database": {"host": "localhost"}},
        config_file.open("w", encoding="utf-8"),
    )

    manager = ConfigManager()
    manager.load(config_file)

    assert manager.get("database.host") == "localhost"


def test_get_missing_key_returns_default(tmp_path: Path) -> None:
    """Missing keys should return the supplied default."""
    config_file = tmp_path / "config.yaml"

    yaml.safe_dump({}, config_file.open("w", encoding="utf-8"))

    manager = ConfigManager()
    manager.load(config_file)

    assert manager.get("missing.key", "default") == "default"


def test_require_existing_key(tmp_path: Path) -> None:
    """Required keys should be returned."""
    config_file = tmp_path / "config.yaml"

    yaml.safe_dump(
        {"server": {"port": 8080}},
        config_file.open("w", encoding="utf-8"),
    )

    manager = ConfigManager()
    manager.load(config_file)

    assert manager.require("server.port") == 8080


def test_require_missing_key(tmp_path: Path) -> None:
    """Missing required keys should raise an exception."""
    config_file = tmp_path / "config.yaml"

    yaml.safe_dump({}, config_file.open("w", encoding="utf-8"))

    manager = ConfigManager()
    manager.load(config_file)

    with pytest.raises(MissingConfigurationError):
        manager.require("server.port")


# ============================================================================
# Contains
# ============================================================================


def test_contains_existing_key(tmp_path: Path) -> None:
    """contains() should return True for existing keys."""
    config_file = tmp_path / "config.yaml"

    yaml.safe_dump(
        {"logging": {"level": "INFO"}},
        config_file.open("w", encoding="utf-8"),
    )

    manager = ConfigManager()
    manager.load(config_file)

    assert manager.contains("logging.level")


def test_contains_missing_key(tmp_path: Path) -> None:
    """contains() should return False for missing keys."""
    config_file = tmp_path / "config.yaml"

    yaml.safe_dump({}, config_file.open("w", encoding="utf-8"))

    manager = ConfigManager()
    manager.load(config_file)

    assert not manager.contains("logging.level")


# ============================================================================
# Export
# ============================================================================


def test_as_dict_returns_copy(tmp_path: Path) -> None:
    """as_dict() should return a mutable copy."""
    config_file = tmp_path / "config.yaml"

    yaml.safe_dump(
        {"value": 10},
        config_file.open("w", encoding="utf-8"),
    )

    manager = ConfigManager()
    manager.load(config_file)

    exported = manager.as_dict()

    assert exported["value"] == 10

    exported["value"] = 20

    assert manager.get("value") == 10


# ============================================================================
# Clear
# ============================================================================


def test_clear_configuration(tmp_path: Path) -> None:
    """clear() should remove all configuration."""
    config_file = tmp_path / "config.yaml"

    yaml.safe_dump(
        {"example": 123},
        config_file.open("w", encoding="utf-8"),
    )

    manager = ConfigManager()
    manager.load(config_file)

    manager.clear()

    assert manager.config == {}