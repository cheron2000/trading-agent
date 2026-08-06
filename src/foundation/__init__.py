"""
AI Trading Operating System - Foundation Layer.

The Foundation Layer provides the core building blocks shared across the
entire AI Trading Operating System. It is intentionally independent of
trading logic, market data, AI, execution, and communication layers.

Public modules:
    - constants
    - enums
    - exceptions
    - logger
    - config_manager
    - base_event
    - base_plugin
    - models
    - utils

Python: 3.13+
"""

from foundation.base_event import BaseEvent
from foundation.base_plugin import BasePlugin
from foundation.config_manager import ConfigManager
from foundation.constants import (
    API_VERSION,
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_LOGGER_NAME,
    EVENT_SCHEMA_VERSION,
    SYSTEM_NAME,
    SYSTEM_SHORT_NAME,
)
from foundation.enums import (
    ComponentState,
    Enablement,
    Environment,
    ExitCode,
    HealthStatus,
    LogLevel,
    PluginState,
    Severity,
    SingletonStatus,
    SortOrder,
)
from foundation.exceptions import (
    ConfigurationError,
    DeserializationError,
    FoundationError,
    FrameworkStateError,
    ImmutableModelError,
    InvalidConfigurationError,
    LoggerError,
    MissingConfigurationError,
    PluginError,
    PluginInitializationError,
    PluginLoadError,
    PluginRegistrationError,
    PluginStateError,
    ResourceAlreadyExistsError,
    ResourceError,
    ResourceNotFoundError,
    SerializationError,
    TimeoutError,
    UnsupportedOperationError,
    ValidationError,
)
from foundation.logger import ILogger, ProductionLogger
from foundation.models.base_model import BaseModel
from foundation.models.metadata import Metadata
from foundation.models.version import Version

__all__ = [
    # Core
    "BaseEvent",
    "BasePlugin",
    "ConfigManager",
    "ILogger",
    "ProductionLogger",
    # Models
    "BaseModel",
    "Metadata",
    "Version",
    # Constants
    "SYSTEM_NAME",
    "SYSTEM_SHORT_NAME",
    "API_VERSION",
    "EVENT_SCHEMA_VERSION",
    "DEFAULT_CONFIG_FILENAME",
    "DEFAULT_LOGGER_NAME",
    # Enums
    "LogLevel",
    "Environment",
    "PluginState",
    "ComponentState",
    "HealthStatus",
    "ExitCode",
    "Severity",
    "SortOrder",
    "Enablement",
    "SingletonStatus",
    # Exceptions
    "FoundationError",
    "ConfigurationError",
    "MissingConfigurationError",
    "InvalidConfigurationError",
    "PluginError",
    "PluginLoadError",
    "PluginInitializationError",
    "PluginRegistrationError",
    "PluginStateError",
    "LoggerError",
    "ValidationError",
    "ImmutableModelError",
    "ResourceError",
    "ResourceNotFoundError",
    "ResourceAlreadyExistsError",
    "SerializationError",
    "DeserializationError",
    "TimeoutError",
    "FrameworkStateError",
    "UnsupportedOperationError",
]
