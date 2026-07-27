"""
data.normalizers.market_normalizer
=====================================

MarketNormalizer — converts raw provider payloads into MarketTick.

Validates all fields strictly. Any malformed input raises ValueError
with a descriptive message — never a silent drop.

Python Version: 3.11+
"""

from __future__ import annotations

from datetime import datetime, timezone

from data.models.market_tick import MarketTick


class MarketNormalizer:
    """Normalizes raw market data dicts into validated MarketTick objects.

    Raw data from external providers is untyped and potentially malformed.
    This normalizer acts as the trust boundary — only well-formed,
    validated MarketTick objects pass through to downstream processing.

    Usage::

        normalizer = MarketNormalizer(source="alpaca")
        tick = normalizer.normalize(raw_dict)
    """

    def __init__(self, source: str = "unknown") -> None:
        """
        Args:
            source: Name of the originating provider. Used as the
                    ``source`` field on produced ``MarketTick`` objects.
        """
        if not source or not source.strip():
            raise ValueError("source must not be empty.")
        self._source = source.strip()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def normalize(self, raw: dict) -> MarketTick:
        """Normalize a raw provider payload into a MarketTick.

        Args:
            raw: Dictionary from a data provider. Must contain keys:
                 ``symbol``, ``price``, ``volume``, ``timestamp``.

        Returns:
            Validated, immutable ``MarketTick``.

        Raises:
            ValueError: If any required field is missing, empty, or
                        fails validation (price <= 0, volume < 0, etc.).
            TypeError:  If ``raw`` is not a dict.
        """
        if not isinstance(raw, dict):
            raise TypeError(f"raw must be a dict, got {type(raw).__name__}.")

        symbol = self._extract_symbol(raw)
        price = self._extract_price(raw)
        volume = self._extract_volume(raw)
        timestamp = self._extract_timestamp(raw)

        return MarketTick(
            symbol=symbol,
            price=price,
            volume=volume,
            timestamp=timestamp,
            source=self._source,
        )

    # ------------------------------------------------------------------
    # Field extractors / validators
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_symbol(raw: dict) -> str:
        if "symbol" not in raw:
            raise ValueError("Missing required field: 'symbol'.")
        value = raw["symbol"]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"'symbol' must be a non-empty string, got: {value!r}.")
        return value.strip().upper()

    @staticmethod
    def _extract_price(raw: dict) -> float:
        if "price" not in raw:
            raise ValueError("Missing required field: 'price'.")
        try:
            price = float(raw["price"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"'price' must be numeric, got: {raw['price']!r}."
            ) from exc
        if price <= 0:
            raise ValueError(f"'price' must be greater than zero, got: {price}.")
        return price

    @staticmethod
    def _extract_volume(raw: dict) -> float:
        if "volume" not in raw:
            raise ValueError("Missing required field: 'volume'.")
        try:
            volume = float(raw["volume"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"'volume' must be numeric, got: {raw['volume']!r}."
            ) from exc
        if volume < 0:
            raise ValueError(f"'volume' must not be negative, got: {volume}.")
        return volume

    @staticmethod
    def _extract_timestamp(raw: dict) -> datetime:
        if "timestamp" not in raw:
            raise ValueError("Missing required field: 'timestamp'.")
        value = raw["timestamp"]
        if isinstance(value, datetime):
            ts = value
        elif isinstance(value, str):
            try:
                ts = datetime.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(
                    f"'timestamp' is not a valid ISO-8601 string: {value!r}."
                ) from exc
        else:
            raise TypeError(
                f"'timestamp' must be a datetime or ISO-8601 string, "
                f"got: {type(value).__name__}."
            )
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
