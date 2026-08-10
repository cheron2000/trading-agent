"""
data.providers.market_provider
================================

MarketDataProvider — fixture-backed market data adapter.

Loads recorded MarketTick data from a JSON fixture file so that
all unit tests run without live network calls. The fixture path
is configurable for testing purposes.

Python Version: 3.11+
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from data.models.market_tick import MarketTick
from data.providers.i_data_provider import IDataProvider

# Default fixture: src/data/providers/ → parents[0]=providers, [1]=data, [2]=src, [3]=project root
_DEFAULT_FIXTURE = (
    Path(__file__).parents[3] / "data_store" / "fixtures" / "market_ticks.json"
)


class MarketDataProvider:
    """Fixture-backed market data provider.

    Loads a JSON fixture on construction and serves MarketTick objects
    by symbol lookup. When the fixture contains multiple entries per
    symbol (e.g. 30 daily rows), each successive call to ``fetch()``
    for that symbol advances to the next entry, cycling back to the
    start when exhausted. This enables realistic price movement across
    simulation days without any live network calls.

    Fixture format (list of tick objects):
    [
        {
            "symbol": "AAPL",
            "price": 182.50,
            "volume": 1200000.0,
            "timestamp": "2024-01-15T14:30:00+00:00",
            "source": "fixture"
        },
        ...
    ]
    """

    SOURCE_NAME: ClassVar[str] = "fixture"

    def __init__(self, fixture_path: Path | str = _DEFAULT_FIXTURE) -> None:
        self._fixture_path = Path(fixture_path)
        # Stores ordered list of ticks per symbol for cycling
        self._tick_lists: dict[str, list[MarketTick]] = {}
        # Current index per symbol — advances on each fetch()
        self._indices: dict[str, int] = {}
        self._load_fixture()

    # ------------------------------------------------------------------
    # IDataProvider implementation
    # ------------------------------------------------------------------

    @property
    def source_name(self) -> str:
        """Return the canonical provider name."""
        return self.SOURCE_NAME

    def fetch(self, symbol: str) -> MarketTick:
        """Return the next fixture tick for a symbol.

        Advances an internal index on each call so successive fetches
        return different daily entries, enabling realistic P&L simulation.
        When all entries for a symbol are exhausted the index wraps back
        to zero (cycles).

        Args:
            symbol: Canonical ticker symbol.

        Returns:
            Immutable ``MarketTick`` from the loaded fixture.

        Raises:
            ValueError: If ``symbol`` is empty or not found in the fixture.
        """
        if not symbol or not symbol.strip():
            raise ValueError("symbol must not be empty.")

        key = symbol.strip().upper()
        if key not in self._tick_lists:
            raise ValueError(
                f"Symbol '{key}' not found in fixture '{self._fixture_path}'."
            )
        ticks = self._tick_lists[key]
        idx = self._indices[key]
        tick = ticks[idx]
        self._indices[key] = (idx + 1) % len(ticks)
        return tick

    def warm_cache(self, symbols: list[str] | None = None) -> None:
        """Warm cache — no-op for fixture provider.

        Fixture data is already loaded in memory, so caching is
        unnecessary. This method exists for compatibility with
        YFinanceProvider, which uses it to pre-fetch data.

        Args:
            symbols: Ignored.
        """

    def fetch_recent(self, symbol: str, n: int = 5) -> list[MarketTick]:
        """Fetch recent ticks for a symbol.

        For fixture provider, returns the next n ticks without advancing
        the main fetch() index.

        Args:
            symbol: Canonical ticker symbol.
            n: Number of recent ticks to return.

        Returns:
            List of immutable ``MarketTick`` objects.

        Raises:
            ValueError: If ``symbol`` is empty or not found.
        """
        if not symbol or not symbol.strip():
            raise ValueError("symbol must not be empty.")

        key = symbol.strip().upper()
        if key not in self._tick_lists:
            raise ValueError(
                f"Symbol '{key}' not found in fixture '{self._fixture_path}'."
            )
        ticks = self._tick_lists[key]
        return ticks[-n:] if len(ticks) >= n else ticks

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_fixture(self) -> None:
        """Load and parse the JSON fixture file."""
        safe_path = Path(self._fixture_path).resolve()
        if not safe_path.exists():
            raise FileNotFoundError(f"Fixture file not found: {safe_path}")

        with safe_path.open("r", encoding="utf-8") as fh:
            raw: list[dict] = json.load(fh)

        for item in raw:
            tick = self._parse_tick(item)
            key = tick.symbol.upper()
            if key not in self._tick_lists:
                self._tick_lists[key] = []
                self._indices[key] = 0
            self._tick_lists[key].append(tick)

    @staticmethod
    def _parse_tick(raw: dict) -> MarketTick:
        """Parse a raw dict into a MarketTick.

        Args:
            raw: Dictionary from the fixture JSON.

        Returns:
            Validated ``MarketTick``.

        Raises:
            ValueError: If required fields are missing or invalid.
            KeyError:   If required keys are absent from the dict.
        """
        try:
            ts_raw = raw["timestamp"]
            if isinstance(ts_raw, str):
                ts = datetime.fromisoformat(ts_raw)
            else:
                raise ValueError("timestamp must be an ISO-8601 string.")

            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            return MarketTick(
                symbol=raw["symbol"],
                price=float(raw["price"]),
                volume=float(raw["volume"]),
                timestamp=ts,
                source=raw.get("source", "fixture"),
            )
        except KeyError as exc:
            raise ValueError(f"Fixture tick missing required field: {exc}") from exc


# Runtime protocol check
assert isinstance(
    MarketDataProvider.__new__(MarketDataProvider), IDataProvider
), "MarketDataProvider does not satisfy the IDataProvider Protocol."
