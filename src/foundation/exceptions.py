"""
Foundation exception hierarchy.

This module defines the common exception classes used throughout the
AI Trading Operating System Foundation Layer.

All custom exceptions should inherit, directly or indirectly, from
FoundationError.

Python: 3.13+
"""

from __future__ import annotations


class FoundationError(Exception):
    """Base class for all framework-specific exceptions."""


# ============================================================================
# Configuration Exceptions
# ============================================================================


class ConfigurationError(FoundationError):
    """Raised when configuration is invalid or cannot be loaded."""


class MissingConfigurationError(ConfigurationError):
    """Raised when a required configuration value is missing."""


class InvalidConfigurationError(ConfigurationError):
    """Raised when a configuration value is invalid."""


# ============================================================================
# Plugin Exceptions
# ============================================================================


class PluginError(FoundationError):
    """Base exception for plugin-related failures."""


class PluginLoadError(PluginError):
    """Raised when a plugin cannot be loaded."""


class PluginInitializationError(PluginError):
    """Raised when plugin initialization fails."""


class PluginRegistrationError(PluginError):
    """Raised when plugin registration fails."""


class PluginStateError(PluginError):
    """Raised when an invalid plugin state transition occurs."""


# ============================================================================
# Logging Exceptions
# ============================================================================


class LoggerError(FoundationError):
    """Raised when the logging subsystem encounters an unrecoverable error."""


# ============================================================================
# Validation Exceptions
# ============================================================================


class ValidationError(FoundationError):
    """Raised when validation of an object fails."""


class ImmutableModelError(ValidationError):
    """Raised when attempting to modify an immutable model."""


# ============================================================================
# Resource Exceptions
# ============================================================================


class ResourceError(FoundationError):
    """Base class for resource-related failures."""


class ResourceNotFoundError(ResourceError):
    """Raised when a requested resource cannot be found."""


class ResourceAlreadyExistsError(ResourceError):
    """Raised when attempting to create an existing resource."""


# ============================================================================
# Serialization Exceptions
# ============================================================================


class SerializationError(FoundationError):
    """Raised when object serialization fails."""


class DeserializationError(FoundationError):
    """Raised when object deserialization fails."""


# ============================================================================
# Timeout Exceptions
# ============================================================================


class TimeoutError(FoundationError):
    """Raised when an internal operation exceeds its timeout."""


# ============================================================================
# Internal Framework Exceptions
# ============================================================================


class FrameworkStateError(FoundationError):
    """Raised when the framework enters an invalid state."""


class UnsupportedOperationError(FoundationError):
    """Raised when an operation is not supported."""
