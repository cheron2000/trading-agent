"""
Foundation enumerations.

This module contains common enumerations shared across the
AI Trading Operating System Foundation Layer.

Only generic, cross-cutting enums belong here. Domain-specific
enums should reside in their respective modules.

Python: 3.13+
"""

from __future__ import annotations

from enum import Enum, IntEnum, StrEnum, auto


class LogLevel(StrEnum):
    """Supported application log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Environment(StrEnum):
    """Application runtime environments."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class PluginState(StrEnum):
    """Lifecycle state of a plugin."""

    CREATED = "created"
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class ComponentState(StrEnum):
    """Generic lifecycle state for framework components."""

    CREATED = "created"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class HealthStatus(StrEnum):
    """Health status reported by framework components."""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ExitCode(IntEnum):
    """Standard process exit codes."""

    SUCCESS = 0
    GENERAL_ERROR = 1
    CONFIGURATION_ERROR = 2
    INITIALIZATION_ERROR = 3
    RUNTIME_ERROR = 4


class Severity(StrEnum):
    """Severity classification for framework events."""

    TRACE = "trace"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SortOrder(StrEnum):
    """Sorting direction."""

    ASCENDING = "ascending"
    DESCENDING = "descending"


class Enablement(StrEnum):
    """Generic enable/disable state."""

    ENABLED = "enabled"
    DISABLED = "disabled"


class SingletonStatus(Enum):
    """Singleton instance status."""

    NOT_CREATED = auto()
    CREATED = auto()