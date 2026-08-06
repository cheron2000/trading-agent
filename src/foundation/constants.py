"""
Foundation-wide immutable constants.

This module defines compile-time constants shared across the
AI Trading Operating System.

These values are intentionally not configurable at runtime.
Runtime configuration belongs in ConfigManager.

Python: 3.13+
"""

from __future__ import annotations

# ============================================================================
# System Information
# ============================================================================

SYSTEM_NAME: str = "AI Trading Operating System"
SYSTEM_SHORT_NAME: str = "AITOS"

DEFAULT_TEXT_ENCODING: str = "utf-8"
DEFAULT_TIMEZONE: str = "UTC"

# ============================================================================
# Versioning
# ============================================================================

API_VERSION: str = "1.0.0"
EVENT_SCHEMA_VERSION: str = "1.0"

# ============================================================================
# Logging
# ============================================================================

DEFAULT_LOGGER_NAME: str = "aitos"

DEFAULT_LOG_FORMAT: str = (
    "%(asctime)s | %(levelname)s | %(name)s | " "%(filename)s:%(lineno)d | %(message)s"
)

DEFAULT_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# ============================================================================
# Plugin System
# ============================================================================

PLUGIN_DIRECTORY_NAME: str = "plugins"

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_CONFIG_FILENAME: str = "config.yaml"

# ============================================================================
# Validation
# ============================================================================

MIN_UUID_LENGTH: int = 36

# ============================================================================
# File Extensions
# ============================================================================

JSON_EXTENSION: str = ".json"
YAML_EXTENSION: str = ".yaml"
YML_EXTENSION: str = ".yml"
LOG_EXTENSION: str = ".log"
