"""
data.providers.i_data_provider
================================

IDataProvider Protocol — contract for all data source adapters.

Implementations must fetch a MarketTick for a given symbol without
making live network calls in unit-test contexts (use fixtures/mocks).

Python Version: 3.11+
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from data.models.market_tick import MarketTick


@runtime_checkable
class IDataProvider(Protocol):
    """Protocol for market data provider adapters.

    All provider implementations must satisfy this interface.
    The contract intentionally keeps fetch() synchronous; async
    variants are a future-phase concern.
    """

    @property
    def source_name(self) -> str:
        """Return the canonical name of this data source.

        Returns:
            Non-empty string identifier, e.g. ``"alpaca"``, ``"fixture"``.
        """
        ...

    def fetch(self, symbol: str) -> MarketTick:
        """Fetch the latest MarketTick for a symbol.

        Args:
            symbol: Canonical ticker symbol (e.g. ``"AAPL"``).

        Returns:
            Normalized, immutable ``MarketTick``.

        Raises:
            ValueError: If ``symbol`` is empty or not found.
            RuntimeError: If the underlying data source is unavailable.
        """
        ...
