"""
Unit tests for foundation.enums.

Python: 3.13+
"""

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


# ============================================================================
# LogLevel
# ============================================================================


def test_log_level_values() -> None:
    """Verify LogLevel string values."""
    assert LogLevel.DEBUG.value == "DEBUG"
    assert LogLevel.INFO.value == "INFO"
    assert LogLevel.WARNING.value == "WARNING"
    assert LogLevel.ERROR.value == "ERROR"
    assert LogLevel.CRITICAL.value == "CRITICAL"


# ============================================================================
# Environment
# ============================================================================


def test_environment_values() -> None:
    """Verify Environment values."""
    assert Environment.DEVELOPMENT.value == "development"
    assert Environment.TESTING.value == "testing"
    assert Environment.STAGING.value == "staging"
    assert Environment.PRODUCTION.value == "production"


# ============================================================================
# PluginState
# ============================================================================


def test_plugin_state_values() -> None:
    """Verify PluginState values."""
    assert PluginState.CREATED.value == "created"
    assert PluginState.INITIALIZED.value == "initialized"
    assert PluginState.RUNNING.value == "running"
    assert PluginState.STOPPED.value == "stopped"
    assert PluginState.FAILED.value == "failed"


# ============================================================================
# ComponentState
# ============================================================================


def test_component_state_values() -> None:
    """Verify ComponentState values."""
    assert ComponentState.CREATED.value == "created"
    assert ComponentState.INITIALIZING.value == "initializing"
    assert ComponentState.READY.value == "ready"
    assert ComponentState.RUNNING.value == "running"
    assert ComponentState.STOPPING.value == "stopping"
    assert ComponentState.STOPPED.value == "stopped"
    assert ComponentState.FAILED.value == "failed"


# ============================================================================
# HealthStatus
# ============================================================================


def test_health_status_values() -> None:
    """Verify HealthStatus values."""
    assert HealthStatus.UNKNOWN.value == "unknown"
    assert HealthStatus.HEALTHY.value == "healthy"
    assert HealthStatus.DEGRADED.value == "degraded"
    assert HealthStatus.UNHEALTHY.value == "unhealthy"


# ============================================================================
# ExitCode
# ============================================================================


def test_exit_code_values() -> None:
    """Verify ExitCode integer values."""
    assert ExitCode.SUCCESS == 0
    assert ExitCode.GENERAL_ERROR == 1
    assert ExitCode.CONFIGURATION_ERROR == 2
    assert ExitCode.INITIALIZATION_ERROR == 3
    assert ExitCode.RUNTIME_ERROR == 4


# ============================================================================
# Severity
# ============================================================================


def test_severity_values() -> None:
    """Verify Severity values."""
    assert Severity.TRACE.value == "trace"
    assert Severity.LOW.value == "low"
    assert Severity.MEDIUM.value == "medium"
    assert Severity.HIGH.value == "high"
    assert Severity.CRITICAL.value == "critical"


# ============================================================================
# SortOrder
# ============================================================================


def test_sort_order_values() -> None:
    """Verify SortOrder values."""
    assert SortOrder.ASCENDING.value == "ascending"
    assert SortOrder.DESCENDING.value == "descending"


# ============================================================================
# Enablement
# ============================================================================


def test_enablement_values() -> None:
    """Verify Enablement values."""
    assert Enablement.ENABLED.value == "enabled"
    assert Enablement.DISABLED.value == "disabled"


# ============================================================================
# SingletonStatus
# ============================================================================


def test_singleton_status_members() -> None:
    """Verify SingletonStatus members exist."""
    assert SingletonStatus.NOT_CREATED is not None
    assert SingletonStatus.CREATED is not None


# ============================================================================
# General Enum Behavior
# ============================================================================


def test_log_level_lookup() -> None:
    """Verify enum lookup by value."""
    assert LogLevel("INFO") is LogLevel.INFO


def test_environment_lookup() -> None:
    """Verify enum lookup by value."""
    assert Environment("production") is Environment.PRODUCTION


def test_plugin_state_lookup() -> None:
    """Verify enum lookup by value."""
    assert PluginState("running") is PluginState.RUNNING


def test_exit_code_is_int() -> None:
    """Verify ExitCode behaves as an integer."""
    assert isinstance(ExitCode.SUCCESS, int)


def test_all_log_levels_are_unique() -> None:
    """Verify LogLevel values are unique."""
    values = {level.value for level in LogLevel}
    assert len(values) == len(LogLevel)


def test_all_plugin_states_are_unique() -> None:
    """Verify PluginState values are unique."""
    values = {state.value for state in PluginState}
    assert len(values) == len(PluginState)