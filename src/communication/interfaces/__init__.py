"""
communication.interfaces
========================

Public API for the Communication Layer interface contracts.

This package contains the canonical Protocol definitions that all
Communication Layer implementations must satisfy. Interfaces are
runtime-checkable and contain zero implementation logic.

Modules:
    i_event_bus:
        IEventBus — publish/subscribe event bus contract.

    i_scheduler:
        IScheduler — recurring callback scheduling contract.

    i_health_monitor:
        IHealthMonitor — component health tracking contract.
"""

from .i_event_bus import IEventBus
from .i_health_monitor import IHealthMonitor
from .i_scheduler import IScheduler

__all__ = (
    "IEventBus",
    "IHealthMonitor",
    "IScheduler",
)
