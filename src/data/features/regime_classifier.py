"""
data.features.regime_classifier
================================

Dynamic market regime classifier using ADX (Average Directional Index)
and ATR volatility ratio to accurately classify market state.

Regimes:
  - TRENDING:       ADX > 25 & ATR ratio < 1.5 → strong directional moves
  - RANGING:        ADX < 20 & ATR ratio < 1.2 → mean-reversion setups
  - HIGH_VOLATILITY: ATR ratio >= 1.5           → breakout/continuation only
  - CRISIS:         ATR ratio >= 2.5            → capital preservation only

Python Version: 3.11+
"""

from __future__ import annotations

from typing import Any


def classify_regime(prices: list[float], period: int = 14) -> dict[str, Any]:
    """Classify market regime from a price series.

    Args:
        prices: List of recent prices (minimum 30 recommended).
        period: Lookback period for ADX and ATR (default 14).

    Returns:
        Dict with keys: regime_label, regime_confidence, adx, atr, atr_ratio.
    """
    n = len(prices)
    if n < period + 2:
        return {
            "regime_label": "trending",
            "regime_confidence": 0.60,
            "adx": 0.0,
            "atr": 0.0,
            "atr_ratio": 1.0,
        }

    # --- Compute ADX ---
    adx = _compute_adx(prices, period)

    # --- Compute ATR and ATR ratio ---
    atr = _compute_atr(prices, period)
    atr_5 = _compute_atr(prices, min(5, n - 1))
    atr_20 = _compute_atr(prices, min(20, n - 1))
    atr_ratio = (atr_5 / atr_20) if atr_20 > 0 else 1.0

    # --- Classify ---
    if atr_ratio >= 2.5:
        regime_label = "crisis"
        regime_confidence = 0.95
    elif atr_ratio >= 1.5:
        regime_label = "volatile"
        regime_confidence = 0.85
    elif adx > 25 and atr_ratio < 1.5:
        regime_label = "trending"
        # Stronger ADX → higher confidence
        regime_confidence = min(0.95, 0.70 + (adx - 25) * 0.005)
    elif adx < 20 and atr_ratio < 1.2:
        regime_label = "ranging"
        regime_confidence = min(0.90, 0.70 + (20 - adx) * 0.01)
    else:
        # Transitional / ambiguous
        regime_label = "trending"
        regime_confidence = 0.65

    return {
        "regime_label": regime_label,
        "regime_confidence": regime_confidence,
        "adx": round(adx, 2),
        "atr": round(atr, 6),
        "atr_ratio": round(atr_ratio, 3),
    }


def _compute_adx(prices: list[float], period: int = 14) -> float:
    """Compute ADX (Average Directional Index) from price series.

    Since we only have a single price series (not OHLC), we approximate:
    - +DM = max(price[i] - price[i-1], 0)
    - -DM = max(price[i-1] - price[i], 0)
    - TR  = abs(price[i] - price[i-1])
    """
    n = len(prices)
    if n < period + 2:
        return 0.0

    plus_dm = []
    minus_dm = []
    true_ranges = []

    for i in range(1, n):
        diff = prices[i] - prices[i - 1]
        tr = abs(diff)
        true_ranges.append(tr)

        if diff > 0:
            plus_dm.append(diff)
            minus_dm.append(0.0)
        else:
            plus_dm.append(0.0)
            minus_dm.append(abs(diff))

    # Smoothed averages over the period
    def _smooth_avg(values: list[float], p: int) -> list[float]:
        """Wilder's smoothing."""
        if len(values) < p:
            return [sum(values) / len(values)] if values else [0.0]
        result = [sum(values[:p]) / p]
        for i in range(p, len(values)):
            result.append((result[-1] * (p - 1) + values[i]) / p)
        return result

    smoothed_tr = _smooth_avg(true_ranges, period)
    smoothed_plus = _smooth_avg(plus_dm, period)
    smoothed_minus = _smooth_avg(minus_dm, period)

    # Compute +DI and -DI
    min_len = min(len(smoothed_tr), len(smoothed_plus), len(smoothed_minus))
    if min_len == 0:
        return 0.0

    dx_values = []
    for i in range(min_len):
        tr_val = smoothed_tr[i]
        if tr_val <= 0:
            continue
        plus_di = (smoothed_plus[i] / tr_val) * 100
        minus_di = (smoothed_minus[i] / tr_val) * 100
        di_sum = plus_di + minus_di
        if di_sum > 0:
            dx_values.append(abs(plus_di - minus_di) / di_sum * 100)

    if not dx_values:
        return 0.0

    # ADX is the smoothed average of DX
    adx_values = _smooth_avg(dx_values, period)
    return adx_values[-1] if adx_values else 0.0


def _compute_atr(prices: list[float], period: int = 14) -> float:
    """Compute ATR from a single price series (approximation)."""
    if len(prices) < 2:
        return 0.0
    true_ranges = [abs(prices[i] - prices[i - 1]) for i in range(1, len(prices))]
    recent = true_ranges[-period:] if len(true_ranges) >= period else true_ranges
    return sum(recent) / len(recent) if recent else 0.0
