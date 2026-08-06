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

    pass


# ============================================================================
# Configuration Exceptions
# ============================================================================


class ConfigurationError(FoundationError):
    """Raised when configuration is invalid or cannot be loaded."""

    pass


class MissingConfigurationError(ConfigurationError):
    """Raised when a required configuration value is missing."""

    pass


class InvalidConfigurationError(ConfigurationError):
    """Raised when a configuration value is invalid."""

    pass


# ============================================================================
# Plugin Exceptions
# ============================================================================


class PluginError(FoundationError):
    """Base exception for plugin-related failures."""

    pass


class PluginLoadError(PluginError):
    """Raised when a plugin cannot be loaded."""

    pass


class PluginInitializationError(PluginError):
    """Raised when plugin initialization fails."""

    pass


class PluginRegistrationError(PluginError):
    """Raised when plugin registration fails."""

    pass


class PluginStateError(PluginError):
    """Raised when an invalid plugin state transition occurs."""

    pass


# ============================================================================
# Logging Exceptions
# ============================================================================


class LoggerError(FoundationError):
    """Raised when the logging subsystem encounters an unrecoverable error."""

    pass


# ============================================================================
# Validation Exceptions
# ============================================================================


class ValidationError(FoundationError):
    """Raised when validation of an object fails."""

    pass


class ImmutableModelError(ValidationError):
    """Raised when attempting to modify an immutable model."""

    pass


# ============================================================================
# Resource Exceptions
# ============================================================================


class ResourceError(FoundationError):
    """Base class for resource-related failures."""

    pass


class ResourceNotFoundError(ResourceError):
    """Raised when a requested resource cannot be found."""

    pass


class ResourceAlreadyExistsError(ResourceError):
    """Raised when attempting to create an existing resource."""

    pass


# ============================================================================
# Serialization Exceptions
# ============================================================================


class SerializationError(FoundationError):
    """Raised when object serialization fails."""

    pass


class DeserializationError(FoundationError):
    """Raised when object deserialization fails."""

    pass


# ============================================================================
# Timeout Exceptions
# ============================================================================


class TimeoutError(FoundationError):
    """Raised when an internal operation exceeds its timeout."""

    pass


# ============================================================================
# Internal Framework Exceptions
# ============================================================================


class FrameworkStateError(FoundationError):
    """Raised when the framework enters an invalid state."""

    pass


class UnsupportedOperationError(FoundationError):
    """Raised when an operation is not supported."""

    pass
