"""
communication.interfaces.i_health_monitor
==========================================

Defines the IHealthMonitor Protocol for the Communication Layer.

This interface specifies the contract for component health tracking
via heartbeat signals. Implementations track liveness and expose
per-component health queries.

Zero implementation logic lives here.

Python Version: 3.11+
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from communication.models.heartbeat import Heartbeat


@runtime_checkable
class IHealthMonitor(Protocol):
    """Protocol defining the HealthMonitor contract.

    Implementations track registered components and their liveness
    based on received ``Heartbeat`` signals.

    Callers depend only on this interface, never on a concrete class.
    """

    def register(self, component_name: str) -> None:
        """Register a component for health monitoring.

        After registration the monitor will track heartbeat signals
        from the named component and report it as monitored.

        Registering the same component name more than once is a no-op.

        Args:
            component_name:
                Unique name of the component to monitor.
                Must not be empty.

        Raises:
            ValueError:
                If ``component_name`` is empty or blank.
        """
        ...

    def record_heartbeat(self, heartbeat: Heartbeat) -> None:
        """Record a heartbeat signal from a component.

        Updates the last-seen timestamp and health state for the
        component identified by ``heartbeat.component_name``.

        Components that have not been explicitly registered via
        ``register`` may be auto-registered on first heartbeat,
        depending on the implementation.

        Args:
            heartbeat:
                Immutable ``Heartbeat`` signal from the component.
                Must not be None.

        Raises:
            ValueError:
                If ``heartbeat`` is None.
        """
        ...

    def is_alive(self, component_name: str) -> bool:
        """Return whether a registered component is considered alive.

        A component is alive when it has sent a heartbeat within the
        implementation-defined liveness window AND its health state
        is operational (RUNNING or DEGRADED).

        Args:
            component_name:
                Name of the component to query.

        Returns:
            True if the component is alive, False if it is unknown,
            timed-out, or in a terminal/non-operational state.
        """
        ...
