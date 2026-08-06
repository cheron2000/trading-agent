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
    | rsi                   | 14-period Relative Strength Index              |
    | macd_line             | MACD line (12 EMA - 26 EMA)                    |
    | macd_signal           | MACD signal line (9-period EMA approx)         |
    | macd_histogram        | MACD line - MACD signal                        |
    | bb_upper              | Bollinger Bands upper (20-period 2 std dev)    |
    | bb_lower              | Bollinger Bands lower (20-period 2 std dev)    |
    | bb_middle             | Bollinger Bands middle (20-period SMA)         |
    | bb_position           | Position within Bollinger Bands (0.0 to 1.0)   |
    | volume_ratio          | Latest volume / mean volume                    |
    | sma_5                 | 5-period Simple Moving Average                 |
    | sma_20                | 20-period Simple Moving Average                |
    | atr                   | 14-period Average True Range                   |
    | atr_pct               | ATR as a percentage of latest price            |
    +-----------------------+------------------------------------------------+

    ``source_quality`` is computed as ``min(len(ticks) / window_size, 1.0)``,
    so a partial window produces a quality score below 1.0.
    """

    DEFAULT_WINDOW_SIZE: ClassVar[int] = 26

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
            (prices[-1] - prices[0]) / prices[0] * 100.0 if prices[0] != 0 else 0.0
        )
        volume_mean = statistics.mean(volumes)
        volume_total = sum(volumes)
        high = max(prices)
        low = min(prices)

        # RSI-14
        rsi = FeatureEngineer._compute_rsi(prices, period=14)

        # MACD
        macd_line = FeatureEngineer._ema(prices, 12) - FeatureEngineer._ema(prices, 26)
        macd_signal = macd_line * (9.0 / (9.0 + 1.0)) if n >= 26 else 0.0
        macd_histogram = macd_line - macd_signal

        # Bollinger Bands
        bb_window = prices[-20:] if n >= 20 else prices
        bb_middle = statistics.mean(bb_window)
        bb_std = statistics.pstdev(bb_window) if len(bb_window) >= 2 else 0.0
        bb_upper = bb_middle + 2 * bb_std
        bb_lower = bb_middle - 2 * bb_std
        bb_position = (
            (price_latest - bb_lower) / (bb_upper - bb_lower)
            if (bb_upper - bb_lower) > 0
            else 0.5
        )

        # Volume Ratio
        volume_ratio = volumes[-1] / volume_mean if volume_mean > 0 else 1.0

        # SMAs
        sma_5 = statistics.mean(prices[-5:]) if n >= 5 else price_latest
        sma_20 = statistics.mean(prices[-20:]) if n >= 20 else price_latest

        # ATR (14-period) and ATR ratio (5-period / 20-period ATR for volatility expansion detection)
        atr = FeatureEngineer._compute_atr(prices, period=14)
        atr_pct = (atr / price_latest * 100.0) if price_latest > 0 else 0.0
        atr_5 = FeatureEngineer._compute_atr(prices, period=5)
        atr_20 = FeatureEngineer._compute_atr(prices, period=20)
        atr_ratio = (atr_5 / atr_20) if atr_20 > 0 else 1.0

        # VWAP calculation
        pv_sum = sum(p * v for p, v in zip(prices, volumes))
        vwap = (pv_sum / volume_total) if volume_total > 0 else price_latest

        # Market Regime Classification
        # 1. Crisis: ATR ratio > 1.75
        # 2. Volatile: ATR ratio > 1.25 or volume_ratio > 1.8
        # 3. Ranging: Price oscillates near VWAP, BB width narrow, RSI between 35-65
        # 4. Trending: Price riding one side of VWAP with directional MACD
        if atr_ratio >= 1.75:
            regime_label = "crisis"
            regime_confidence = 0.90
        elif atr_ratio >= 1.25 or volume_ratio > 1.8:
            regime_label = "volatile"
            regime_confidence = 0.85
        elif (
            (abs(price_latest - vwap) / vwap < 0.01)
            and (35 <= rsi <= 65)
            and ((bb_upper - bb_lower) / bb_middle < 0.04 if bb_middle > 0 else True)
        ):
            regime_label = "ranging"
            regime_confidence = 0.80
        else:
            regime_label = "trending"
            regime_confidence = 0.85

        return {
            "price_latest": price_latest,
            "price_mean": price_mean,
            "price_std": price_std,
            "price_change_pct": price_change_pct,
            "volume_mean": volume_mean,
            "volume_total": volume_total,
            "high": high,
            "low": low,
            "rsi": rsi,
            "macd_line": macd_line,
            "macd_signal": macd_signal,
            "macd_histogram": macd_histogram,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "bb_middle": bb_middle,
            "bb_position": bb_position,
            "volume_ratio": volume_ratio,
            "sma_5": sma_5,
            "sma_20": sma_20,
            "atr": atr,
            "atr_pct": atr_pct,
            "atr_ratio": atr_ratio,
            "vwap": vwap,
            "regime_label": regime_label,
            "regime_confidence": regime_confidence,
        }

    @staticmethod
    def _compute_atr(prices: list[float], period: int = 14) -> float:
        """Compute Average True Range (ATR) as a volatility measure.

        For simplicity with single price series (no OHLC), True Range is
        approximated as abs(prices[i] - prices[i-1]).
        """
        if len(prices) < 2:
            return 0.0
        true_ranges = [abs(prices[i] - prices[i - 1]) for i in range(1, len(prices))]
        recent = true_ranges[-period:] if len(true_ranges) >= period else true_ranges
        return sum(recent) / len(recent) if recent else 0.0

    @staticmethod
    def _compute_rsi(prices: list[float], period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50.0
        changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        gains = [max(c, 0.0) for c in changes[-period:]]
        losses = [abs(min(c, 0.0)) for c in changes[-period:]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def _ema(prices: list[float], period: int) -> float:
        if not prices:
            return 0.0
        k = 2.0 / (period + 1)
        ema = prices[0]
        for p in prices[1:]:
            ema = p * k + ema * (1 - k)
        return ema

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def window_size(self) -> int:
        """Return the configured window size."""
        return self._window_size
