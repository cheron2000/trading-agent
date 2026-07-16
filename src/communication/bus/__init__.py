"""
communication.bus
=================

Concrete Transport & EventBus implementations for the Communication Layer.

This package provides the in-memory EventBus and thread-based Scheduler
that power all intra-system event routing in the AI Trading OS.

Modules:
    event_bus:
        EventBus — thread-safe in-memory pub/sub implementing IEventBus.

    scheduler:
        Scheduler — recurring thread-based callbacks implementing IScheduler.
"""

from .event_bus import EventBus
from .scheduler import Scheduler

__all__ = (
    "EventBus",
    "Scheduler",
)
