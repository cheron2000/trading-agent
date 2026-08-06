"""
data.models.feature_vector
===========================

FeatureVector — engineered features ready for the Intelligence Layer.

A FeatureVector is produced by the feature engineering pipeline from
one or more MarketTick observations. It is the canonical input to
the Intelligence Layer (Athena) via FeatureVectorEvent.

Python Version: 3.11+
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class FeatureVector:
    """Immutable engineered feature set for a symbol at a point in time.

    Attributes:
        symbol:         Canonical ticker symbol.
        timestamp:      UTC timestamp this vector represents.
        features:       Named float features (e.g. sma_20, rsi_14).
        source_quality: Confidence in the underlying data (0.0–1.0).
    """

    symbol: str
    timestamp: datetime
    features: dict[str, float]
    source_quality: float

    # ------------------------------------------------------------------
    # Validation constants
    # ------------------------------------------------------------------

    _MAX_SYMBOL_LENGTH: ClassVar[int] = 32
    _MIN_SOURCE_QUALITY: ClassVar[float] = 0.0
    _MAX_SOURCE_QUALITY: ClassVar[float] = 1.0

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must not be empty.")
        if len(self.symbol) > self._MAX_SYMBOL_LENGTH:
            raise ValueError("symbol exceeds maximum length.")
        if self.timestamp is None:
            raise ValueError("timestamp must not be None.")
        if not isinstance(self.features, dict):
            raise TypeError("features must be a dict.")
        if not (self._MIN_SOURCE_QUALITY <= self.source_quality <= self._MAX_SOURCE_QUALITY):
            raise ValueError("source_quality must be between 0.0 and 1.0.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def timestamp_utc(self) -> datetime:
        """Return timestamp guaranteed to be UTC-aware."""
        if self.timestamp.tzinfo is None:
            return self.timestamp.replace(tzinfo=timezone.utc)
        return self.timestamp

    @property
    def feature_count(self) -> int:
        """Return the number of features in this vector."""
        return len(self.features)

    def to_dict(self) -> dict[str, object]:
        """Serialize deterministically."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp_utc.isoformat(),
            "features": dict(self.features),
            "source_quality": self.source_quality,
        }

    def __str__(self) -> str:
        return (
            f"FeatureVector(symbol='{self.symbol}', "
            f"features={self.feature_count}, "
            f"quality={self.source_quality:.2f})"
        )
