"""
communication.models
====================

Public API for the Communication Layer immutable data models.

This package contains the canonical communication contracts used
throughout the AI Trading Operating System. All models are immutable,
transport-agnostic, and safe for concurrent read access.

Only the symbols exported through this module are considered part of the
public Communication Layer API.

Modules:
    event_priority:
        Canonical event priority enumeration.

    health_state:
        Standardized component health lifecycle.

    subscription:
        Immutable subscription descriptor.

    event_metadata:
        Communication-specific metadata associated with an event.

    heartbeat:
        Immutable heartbeat model used for health reporting.

    plugin_manifest:
        Immutable plugin manifest definition.

    event_envelope:
        Canonical communication envelope wrapping a Foundation
        BaseEvent together with communication metadata.
"""

from .event_envelope import EventEnvelope
from .event_metadata import EventMetadata
from .event_priority import EventPriority
from .health_state import HealthState
from .heartbeat import Heartbeat
from .plugin_manifest import PluginManifest
from .subscription import Subscription

__all__ = (
    "EventEnvelope",
    "EventMetadata",
    "EventPriority",
    "HealthState",
    "Heartbeat",
    "PluginManifest",
    "Subscription",
)