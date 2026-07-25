"""
Unit tests for foundation.base_plugin.

Python: 3.13+
"""

from __future__ import annotations

from foundation.base_plugin import BasePlugin
from foundation.enums import PluginState


class TestPlugin(BasePlugin):
    """Concrete plugin implementation for testing."""

    @property
    def name(self) -> str:
        """Return the plugin name."""
        return "test_plugin"

    @property
    def version(self) -> str:
        """Return the plugin version."""
        return "1.0.0"

    def initialize(self) -> None:
        """Initialize the plugin."""
        self._state = PluginState.INITIALIZED

    def start(self) -> None:
        """Start the plugin."""
        self._state = PluginState.RUNNING

    def stop(self) -> None:
        """Stop the plugin."""
        self._state = PluginState.STOPPED

    def shutdown(self) -> None:
        """Shutdown the plugin."""
        self._state = PluginState.STOPPED

    def health_check(self) -> bool:
        """Return plugin health."""
        return self._state is not PluginState.FAILED


# ============================================================================
# Construction
# ============================================================================


def test_plugin_initial_state() -> None:
    """A newly created plugin should be in the CREATED state."""
    plugin = TestPlugin()

    assert plugin.state is PluginState.CREATED


def test_plugin_name() -> None:
    """Plugin should expose its name."""
    plugin = TestPlugin()

    assert plugin.name == "test_plugin"


def test_plugin_version() -> None:
    """Plugin should expose its version."""
    plugin = TestPlugin()

    assert plugin.version == "1.0.0"


# ============================================================================
# Lifecycle
# ============================================================================


def test_initialize_changes_state() -> None:
    """Initialization should update the plugin state."""
    plugin = TestPlugin()

    plugin.initialize()

    assert plugin.state is PluginState.INITIALIZED
    assert plugin.is_initialized()


def test_start_changes_state() -> None:
    """Starting the plugin should set the RUNNING state."""
    plugin = TestPlugin()

    plugin.initialize()
    plugin.start()

    assert plugin.state is PluginState.RUNNING
    assert plugin.is_running()


def test_stop_changes_state() -> None:
    """Stopping the plugin should set the STOPPED state."""
    plugin = TestPlugin()

    plugin.initialize()
    plugin.start()
    plugin.stop()

    assert plugin.state is PluginState.STOPPED
    assert not plugin.is_running()


def test_shutdown_changes_state() -> None:
    """Shutdown should stop the plugin."""
    plugin = TestPlugin()

    plugin.initialize()
    plugin.start()
    plugin.shutdown()

    assert plugin.state is PluginState.STOPPED


# ============================================================================
# Health
# ============================================================================


def test_health_check_returns_true() -> None:
    """Healthy plugin should report True."""
    plugin = TestPlugin()

    assert plugin.health_check() is True


def test_health_check_returns_false_when_failed() -> None:
    """Failed plugin should report unhealthy."""
    plugin = TestPlugin()

    plugin._state = PluginState.FAILED

    assert plugin.health_check() is False


# ============================================================================
# Helper Methods
# ============================================================================


def test_is_initialized_before_initialization() -> None:
    """Plugin should not report initialized before initialization."""
    plugin = TestPlugin()

    assert not plugin.is_initialized()


def test_is_running_before_start() -> None:
    """Plugin should not report running before start."""
    plugin = TestPlugin()

    assert not plugin.is_running()


# ============================================================================
# Representation
# ============================================================================


def test_repr_contains_metadata() -> None:
    """repr() should include identifying information."""
    plugin = TestPlugin()

    text = repr(plugin)

    assert "TestPlugin" in text
    assert "test_plugin" in text
    assert "1.0.0" in text
    assert "created" in text.lower()