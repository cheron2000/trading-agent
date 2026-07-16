"""
data.events.feature_vector_event
==================================

FeatureVectorEvent — published on the EventBus for the Intelligence Layer.

This event carries a complete FeatureVector as a flat payload so that
Athena can consume it without importing from the Data layer directly.

Published by: Data Layer (Orion) after feature engineering.
Consumed by:  Intelligence Layer (Athena) strategy runners.

Python Version: 3.11+
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from foundation.base_event import BaseEvent


@dataclass(frozen=True, slots=True)
class FeatureVectorEvent(BaseEvent):
    """Event carrying engineered features for a symbol.

    Inherits identity fields from BaseEvent (event_id, occurred_at,
    schema_version, correlation_id, causation_id).

    Attributes:
        symbol:         Canonical ticker symbol.
        timestamp:      UTC timestamp the features represent.
        features:       Named float feature map.
        source_quality: Data confidence score (0.0–1.0).
    """

    symbol: str = ""
    timestamp: datetime = None  # type: ignore[assignment]
    features: dict[str, float] = None  # type: ignore[assignment]
    source_quality: float = 1.0

    def __post_init__(self) -> None:
        # BaseEvent is kw_only + frozen — no super().__post_init__ needed.
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must not be empty.")
        if self.timestamp is None:
            raise ValueError("timestamp must not be None.")
        if self.features is None:
            raise ValueError("features must not be None.")
        if not (0.0 <= self.source_quality <= 1.0):
            raise ValueError("source_quality must be between 0.0 and 1.0.")

    def to_dict(self) -> dict[str, object]:
        """Extend BaseEvent serialization with Data layer fields."""
        base = super().to_dict()
        base.update(
            {
                "symbol": self.symbol,
                "timestamp": (
                    self.timestamp.isoformat()
                    if self.timestamp is not None
                    else None
                ),
                "features": dict(self.features) if self.features else {},
                "source_quality": self.source_quality,
            }
        )
        return base
