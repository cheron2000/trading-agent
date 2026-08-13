import time
import logging

logger = logging.getLogger(__name__)


class SupportResistanceCalculator:
    """
    Identifies key support and resistance levels from a price series
    using swing high/low detection.

    A swing high is a price point higher than its N neighbors on both sides.
    A swing low is a price point lower than its N neighbors on both sides.

    Returns the 2 nearest support levels (below current price) and
    2 nearest resistance levels (above current price).

    Caching:
      - Results are cached per symbol with a 15-minute TTL.
    """

    def __init__(self, swing_window: int = 5, cache_ttl_seconds: float = 900.0) -> None:
        self.swing_window = swing_window
        self.cache_ttl_seconds = cache_ttl_seconds

        # {symbol: (supports, resistances, nearest_support, nearest_resistance, supp_dist, res_dist, cached_at)}
        self._cache: dict[str, tuple[dict, float]] = {}

    def _cluster_levels(
        self, levels: list[float], threshold_pct: float = 0.5
    ) -> list[float]:
        """Merge levels within threshold_pct of each other."""
        if not levels:
            return []
        sorted_levels = sorted(levels)
        clusters = [[sorted_levels[0]]]
        for level in sorted_levels[1:]:
            if (level - clusters[-1][-1]) / clusters[-1][-1] * 100 < threshold_pct:
                clusters[-1].append(level)
            else:
                clusters.append([level])
        return [sum(c) / len(c) for c in clusters]

    def calculate(self, symbol: str, prices: list[float], current_price: float) -> dict:
        """
        Returns a dictionary containing the nearest support and resistance levels.
        """
        from typing import Any
        empty_result: dict[str, Any] = {
            "supports": [],
            "resistances": [],
            "nearest_support": None,
            "nearest_resistance": None,
            "support_distance_pct": None,
            "resistance_distance_pct": None,
        }

        if len(prices) < 2 * self.swing_window + 1 or current_price <= 0:
            return empty_result

        now = time.monotonic()
        if symbol in self._cache:
            cached_result, cached_at = self._cache[symbol]
            if (now - cached_at) < self.cache_ttl_seconds:
                return cached_result

        swing_highs = []
        swing_lows = []

        for i in range(self.swing_window, len(prices) - self.swing_window):
            left_window = prices[i - self.swing_window : i]
            right_window = prices[i + 1 : i + 1 + self.swing_window]

            if prices[i] > max(left_window) and prices[i] > max(right_window):
                swing_highs.append(prices[i])

            if prices[i] < min(left_window) and prices[i] < min(right_window):
                swing_lows.append(prices[i])

        clustered_highs = self._cluster_levels(swing_highs)
        clustered_lows = self._cluster_levels(swing_lows)

        supports = sorted(
            [level for level in clustered_lows if level < current_price], reverse=True
        )[:2]
        resistances = sorted(
            [level for level in clustered_highs if level > current_price]
        )[:2]

        nearest_support = supports[0] if supports else None
        nearest_resistance = resistances[0] if resistances else None

        support_distance_pct = (
            ((nearest_support - current_price) / current_price * 100)
            if nearest_support
            else None
        )
        resistance_distance_pct = (
            ((nearest_resistance - current_price) / current_price * 100)
            if nearest_resistance
            else None
        )

        result = {
            "supports": supports,
            "resistances": resistances,
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
            "support_distance_pct": support_distance_pct,
            "resistance_distance_pct": resistance_distance_pct,
        }

        if supports or resistances:
            self._cache[symbol] = (result, now)

        return result
