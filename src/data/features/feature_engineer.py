"""
data.features.feature_engineer
================================

FeatureEngineer — computes deterministic features from a MarketTick window.

Takes a list of MarketTick objects representing a rolling observation
window and produces a FeatureVector ready for the Intelligence Layer.

Design constraints:
- Fully deterministic: same input always produces same output.
- No randomness, no external calls.
- Uses stdlib statistics only.

Python Version: 3.11+
"""

from __future__ import annotations

import statistics
from typing import ClassVar

from data.models.market_tick import MarketTick
from data.models.feature_vector import FeatureVector


class FeatureEngineer:
    """Computes a fixed set of deterministic features from a tick window.

    Features produced:

    +-----------------------+------------------------------------------------+
    | Feature key           | Formula                                        |
    +=======================+================================================+
    | price_latest          | Last tick price                                |
    | price_mean            | Mean of all prices                             |
    | price_std             | Std dev of prices (0.0 if window < 2)          |
    | price_change_pct      | (last - first) / first * 100                   |
    | volume_mean           | Mean volume                                    |
    | volume_total          | Sum of all volumes                             |
    | high                  | Max price in window                            |
    | low                   | Min price in window                            |
    +-----------------------+------------------------------------------------+

    ``source_quality`` is computed as ``min(len(ticks) / window_size, 1.0)``,
    so a partial window produces a quality score below 1.0.
    """

    DEFAULT_WINDOW_SIZE: ClassVar[int] = 20

    def __init__(self, window_size: int = DEFAULT_WINDOW_SIZE) -> None:
        """
        Args:
            window_size:
                Expected number of ticks for a full-quality window.
                Must be >= 1.

        Raises:
            ValueError: If ``window_size`` is less than 1.
        """
        if window_size < 1:
            raise ValueError("window_size must be at least 1.")
        self._window_size = window_size

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute(self, ticks: list[MarketTick]) -> FeatureVector:
        """Compute a FeatureVector from a list of MarketTick observations.

        Args:
            ticks:
                Non-empty list of ``MarketTick`` objects. All ticks must
                share the same ``symbol``.

        Returns:
            Immutable ``FeatureVector`` with computed features and a
            ``source_quality`` score reflecting window fullness.

        Raises:
            ValueError:
                - If ``ticks`` is empty.
                - If ``ticks`` contains more than one distinct symbol.
        """
        if not ticks:
            raise ValueError("ticks must not be empty.")

        symbols = {t.symbol for t in ticks}
        if len(symbols) > 1:
            raise ValueError(
                f"All ticks must share the same symbol. "
                f"Found multiple: {sorted(symbols)}."
            )

        symbol = ticks[0].symbol
        prices = [t.price for t in ticks]
        volumes = [t.volume for t in ticks]

        features = self._compute_features(prices, volumes)
        source_quality = min(len(ticks) / self._window_size, 1.0)
        timestamp = max(ticks, key=lambda t: t.timestamp).timestamp

        return FeatureVector(
            symbol=symbol,
            timestamp=timestamp,
            features=features,
            source_quality=source_quality,
        )

    # ------------------------------------------------------------------
    # Internal feature computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_features(
        prices: list[float],
        volumes: list[float],
    ) -> dict[str, float]:
        """Compute all features from price and volume sequences."""
        n = len(prices)

        price_latest = prices[-1]
        price_mean = statistics.mean(prices)
        price_std = statistics.pstdev(prices) if n >= 2 else 0.0
        price_change_pct = (
            (prices[-1] - prices[0]) / prices[0] * 100.0
            if prices[0] != 0
            else 0.0
        )
        volume_mean = statistics.mean(volumes)
        volume_total = sum(volumes)
        high = max(prices)
        low = min(prices)

        return {
            "price_latest": price_latest,
            "price_mean": price_mean,
            "price_std": price_std,
            "price_change_pct": price_change_pct,
            "volume_mean": volume_mean,
            "volume_total": volume_total,
            "high": high,
            "low": low,
        }

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def window_size(self) -> int:
        """Return the configured window size."""
        return self._window_size
