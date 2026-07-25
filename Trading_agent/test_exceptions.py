"""
Unit tests for foundation.exceptions.

Python: 3.13+
"""

import pytest

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


# ============================================================================
# FoundationError
# ============================================================================


def test_foundation_error_is_exception() -> None:
    """FoundationError should inherit from Exception."""
    assert issubclass(FoundationError, Exception)


def test_foundation_error_message() -> None:
    """FoundationError should preserve its message."""
    message = "foundation failure"

    with pytest.raises(FoundationError, match=message):
        raise FoundationError(message)


# ============================================================================
# Configuration Exceptions
# ============================================================================


def test_configuration_error_inheritance() -> None:
    """ConfigurationError should inherit FoundationError."""
    assert issubclass(ConfigurationError, FoundationError)


def test_missing_configuration_error_inheritance() -> None:
    """MissingConfigurationError should inherit ConfigurationError."""
    assert issubclass(
        MissingConfigurationError,
        ConfigurationError,
    )


def test_invalid_configuration_error_inheritance() -> None:
    """InvalidConfigurationError should inherit ConfigurationError."""
    assert issubclass(
        InvalidConfigurationError,
        ConfigurationError,
    )


# ============================================================================
# Plugin Exceptions
# ============================================================================


def test_plugin_error_inheritance() -> None:
    """PluginError should inherit FoundationError."""
    assert issubclass(PluginError, FoundationError)


def test_plugin_load_error_inheritance() -> None:
    """PluginLoadError should inherit PluginError."""
    assert issubclass(
        PluginLoadError,
        PluginError,
    )


def test_plugin_initialization_error_inheritance() -> None:
    """PluginInitializationError should inherit PluginError."""
    assert issubclass(
        PluginInitializationError,
        PluginError,
    )


def test_plugin_registration_error_inheritance() -> None:
    """PluginRegistrationError should inherit PluginError."""
    assert issubclass(
        PluginRegistrationError,
        PluginError,
    )


def test_plugin_state_error_inheritance() -> None:
    """PluginStateError should inherit PluginError."""
    assert issubclass(
        PluginStateError,
        PluginError,
    )


# ============================================================================
# Validation Exceptions
# ============================================================================


def test_validation_error_inheritance() -> None:
    """ValidationError should inherit FoundationError."""
    assert issubclass(
        ValidationError,
        FoundationError,
    )


def test_immutable_model_error_inheritance() -> None:
    """ImmutableModelError should inherit ValidationError."""
    assert issubclass(
        ImmutableModelError,
        ValidationError,
    )


# ============================================================================
# Resource Exceptions
# ============================================================================


def test_resource_error_inheritance() -> None:
    """ResourceError should inherit FoundationError."""
    assert issubclass(
        ResourceError,
        FoundationError,
    )


def test_resource_not_found_error_inheritance() -> None:
    """ResourceNotFoundError should inherit ResourceError."""
    assert issubclass(
        ResourceNotFoundError,
        ResourceError,
    )


def test_resource_already_exists_error_inheritance() -> None:
    """ResourceAlreadyExistsError should inherit ResourceError."""
    assert issubclass(
        ResourceAlreadyExistsError,
        ResourceError,
    )


# ============================================================================
# Serialization Exceptions
# ============================================================================


def test_serialization_error_inheritance() -> None:
    """SerializationError should inherit FoundationError."""
    assert issubclass(
        SerializationError,
        FoundationError,
    )


def test_deserialization_error_inheritance() -> None:
    """DeserializationError should inherit FoundationError."""
    assert issubclass(
        DeserializationError,
        FoundationError,
    )


# ============================================================================
# Miscellaneous Exceptions
# ============================================================================


def test_logger_error_inheritance() -> None:
    """LoggerError should inherit FoundationError."""
    assert issubclass(
        LoggerError,
        FoundationError,
    )


def test_timeout_error_inheritance() -> None:
    """TimeoutError should inherit FoundationError."""
    assert issubclass(
        TimeoutError,
        FoundationError,
    )


def test_framework_state_error_inheritance() -> None:
    """FrameworkStateError should inherit FoundationError."""
    assert issubclass(
        FrameworkStateError,
        FoundationError,
    )


def test_unsupported_operation_error_inheritance() -> None:
    """UnsupportedOperationError should inherit FoundationError."""
    assert issubclass(
        UnsupportedOperationError,
        FoundationError,
    )


# ============================================================================
# Exception Messages
# ============================================================================


@pytest.mark.parametrize(
    ("exception_type", "message"),
    [
        (ConfigurationError, "config"),
        (PluginLoadError, "plugin"),
        (ValidationError, "validation"),
        (SerializationError, "serialization"),
        (DeserializationError, "deserialization"),
        (LoggerError, "logger"),
        (TimeoutError, "timeout"),
        (FrameworkStateError, "framework"),
        (UnsupportedOperationError, "unsupported"),
    ],
)
def test_exception_message(
    exception_type: type[Exception],
    message: str,
) -> None:
    """Exceptions should preserve the supplied message."""
    with pytest.raises(exception_type, match=message):
        raise exception_type(message)