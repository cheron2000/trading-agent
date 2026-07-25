"""
Defines the abstract BasePlugin contract for the AI Trading Operating System.

Every plugin in the system must inherit from BasePlugin. The framework
manages plugin lifecycle through this interface, ensuring a consistent,
production-quality contract across all plugin implementations.

Python: 3.13+
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from foundation.enums import PluginState


class BasePlugin(ABC):
    """Abstract base class for all framework plugins.

    Every plugin has a unique name, semantic version, and lifecycle state.
    Concrete implementations are responsible for initialization, startup,
    shutdown, and cleanup.

    Attributes:
        _state: Current lifecycle state of the plugin.
    """

    def __init__(self) -> None:
        """Initialize the plugin with the default lifecycle state."""
        self._state: PluginState = PluginState.CREATED

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique plugin name.

        Returns:
            Unique plugin identifier.
        """

    @property
    @abstractmethod
    def version(self) -> str:
        """Return the plugin semantic version.

        Returns:
            Semantic version string.
        """

    @property
    def state(self) -> PluginState:
        """Return the current plugin lifecycle state.

        Returns:
            Current PluginState.
        """
        return self._state

    @abstractmethod
    def initialize(self) -> None:
        """Initialize the plugin and allocate required resources."""

    @abstractmethod
    def start(self) -> None:
        """Start the plugin."""

    @abstractmethod
    def stop(self) -> None:
        """Gracefully stop the plugin."""

    @abstractmethod
    def shutdown(self) -> None:
        """Release all resources owned by the plugin."""

    @abstractmethod
    def health_check(self) -> bool:
        """Determine whether the plugin is healthy.

        Returns:
            True if the plugin is healthy, otherwise False.
        """

    def is_running(self) -> bool:
        """Return whether the plugin is currently running.

        Returns:
            True if the plugin state is RUNNING.
        """
        return self._state is PluginState.RUNNING

    def is_initialized(self) -> bool:
        """Return whether the plugin has been initialized.

        Returns:
            True if the plugin has completed initialization.
        """
        return self._state in (
            PluginState.INITIALIZED,
            PluginState.RUNNING,
        )

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return (
            f"{self.__class__.__name__}("
            f"name='{self.name}', "
            f"version='{self.version}', "
            f"state='{self.state.value}')"
        )