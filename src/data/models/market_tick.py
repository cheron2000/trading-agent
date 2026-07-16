"""
data.models.market_tick
========================

Canonical normalized market tick for the Data Layer (Orion).

A MarketTick is the standardized representation of a single price/volume
observation after provider-specific raw payloads have been normalized.
All downstream processing consumes MarketTick, never raw provider data.

Python Version: 3.11+
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class MarketTick:
    """Immutable canonical market tick.

    Attributes:
        symbol:     Canonical ticker symbol (e.g. "AAPL", "BTC-USD").
        price:      Last traded price. Must be > 0.
        volume:     Volume for this observation. Must be >= 0.
        timestamp:  UTC timestamp of the observation.
        source:     Name of the originating data provider.
    """

    symbol: str
    price: float
    volume: float
    timestamp: datetime
    source: str

    # ------------------------------------------------------------------
    # Validation constants
    # ------------------------------------------------------------------

    _MAX_SYMBOL_LENGTH: ClassVar[int] = 32
    _MAX_SOURCE_LENGTH: ClassVar[int] = 128

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must not be empty.")
        if len(self.symbol) > self._MAX_SYMBOL_LENGTH:
            raise ValueError("symbol exceeds maximum length.")
        if self.price <= 0:
            raise ValueError("price must be greater than zero.")
        if self.volume < 0:
            raise ValueError("volume must not be negative.")
        if self.timestamp is None:
            raise ValueError("timestamp must not be None.")
        if not self.source or not self.source.strip():
            raise ValueError("source must not be empty.")
        if len(self.source) > self._MAX_SOURCE_LENGTH:
            raise ValueError("source exceeds maximum length.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def timestamp_utc(self) -> datetime:
        """Return timestamp guaranteed to be UTC-aware."""
        if self.timestamp.tzinfo is None:
            return self.timestamp.replace(tzinfo=timezone.utc)
        return self.timestamp

    def to_dict(self) -> dict[str, object]:
        """Serialize deterministically."""
        return {
            "symbol": self.symbol,
            "price": self.price,
            "volume": self.volume,
            "timestamp": self.timestamp_utc.isoformat(),
            "source": self.source,
        }

    def __str__(self) -> str:
        return (
            f"MarketTick(symbol='{self.symbol}', "
            f"price={self.price}, volume={self.volume}, "
            f"source='{self.source}')"
        )
