"""
communication.health
====================

Health monitoring implementation for the Communication Layer.

This package provides the HealthMonitor that tracks component liveness
via Heartbeat signals and integrates with the EventBus.

Modules:
    health_monitor:
        HealthMonitor — liveness tracking implementing IHealthMonitor.
"""

from .health_monitor import HealthMonitor

__all__ = ("HealthMonitor",)
