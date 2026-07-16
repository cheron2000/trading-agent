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

# Default fixture relative to project root
_DEFAULT_FIXTURE = Path(__file__).parents[4] / "data_store" / "fixtures" / "market_ticks.json"


class MarketDataProvider:
    """Fixture-backed market data provider.

    Loads a JSON fixture on construction and serves MarketTick objects
    by symbol lookup. Intended for development and testing; a live
    provider would implement the same IDataProvider interface.

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
        self._ticks: dict[str, MarketTick] = {}
        self._load_fixture()

    # ------------------------------------------------------------------
    # IDataProvider implementation
    # ------------------------------------------------------------------

    @property
    def source_name(self) -> str:
        """Return the canonical provider name."""
        return self.SOURCE_NAME

    def fetch(self, symbol: str) -> MarketTick:
        """Return the latest fixture tick for a symbol.

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
        if key not in self._ticks:
            raise ValueError(
                f"Symbol '{key}' not found in fixture '{self._fixture_path}'."
            )
        return self._ticks[key]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_fixture(self) -> None:
        """Load and parse the JSON fixture file."""
        safe_path = Path(self._fixture_path).resolve()
        if not safe_path.exists():
            raise FileNotFoundError(
                f"Fixture file not found: {safe_path}"
            )

        with safe_path.open("r", encoding="utf-8") as fh:
            raw: list[dict] = json.load(fh)

        for item in raw:
            tick = self._parse_tick(item)
            self._ticks[tick.symbol.upper()] = tick

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
assert isinstance(MarketDataProvider.__new__(MarketDataProvider), IDataProvider), (
    "MarketDataProvider does not satisfy the IDataProvider Protocol."
)
