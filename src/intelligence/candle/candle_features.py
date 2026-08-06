"""
intelligence.candle.candle_features
=====================================
Pure candle-pattern feature extraction. No I/O, no project imports.
"""

from __future__ import annotations


def extract(candles: list[dict]) -> dict[str, float]:
    """Extract candle-pattern features from a list of OHLCV dicts.

    Returns {} if fewer than 11 candles (not enough for momentum_10).
    All values are float.
    """
    if len(candles) < 11:
        return {}

    opens = [float(c["open"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    closes = [float(c["close"]) for c in candles]
    vols = [float(c["volume"]) for c in candles]

    n = len(candles)

    def _mean(seq: list[float]) -> float:
        return sum(seq) / len(seq) if seq else 0.0

    # Body sizes
    bodies = [
        abs(closes[i] - opens[i]) / opens[i] if opens[i] else 0.0 for i in range(n)
    ]
    body_size_mean = _mean(bodies)
    body_size_last = bodies[-1]

    # Wick ratios
    upper_wicks = [
        (highs[i] - max(opens[i], closes[i])) / opens[i] if opens[i] else 0.0
        for i in range(n)
    ]
    lower_wicks = [
        (min(opens[i], closes[i]) - lows[i]) / opens[i] if opens[i] else 0.0
        for i in range(n)
    ]
    upper_wick_mean = _mean(upper_wicks)
    lower_wick_mean = _mean(lower_wicks)

    # Bullish fraction
    close_above_open_pct = sum(1.0 for i in range(n) if closes[i] > opens[i]) / n

    # Momentum
    momentum_3 = (closes[-1] - closes[-4]) / closes[-4] * 100 if closes[-4] else 0.0
    momentum_10 = (closes[-1] - closes[-11]) / closes[-11] * 100 if closes[-11] else 0.0

    # Volume trend
    if n >= 20:
        vol_recent = _mean(vols[-5:])
        vol_baseline = _mean(vols[-20:])
        volume_trend = vol_recent / vol_baseline if vol_baseline else 1.0
    else:
        volume_trend = 1.0

    # Engulfing patterns (last two candles)
    prev_o, prev_c = opens[-2], closes[-2]
    last_o, last_c = opens[-1], closes[-1]
    prev_bearish = prev_c < prev_o
    prev_bullish = prev_c > prev_o
    engulfing_bullish = (
        1.0 if (prev_bearish and last_c > prev_o and last_o < prev_c) else 0.0
    )
    engulfing_bearish = (
        1.0 if (prev_bullish and last_c < prev_o and last_o > prev_c) else 0.0
    )

    # Doji: body < 10% of range
    last_range = highs[-1] - lows[-1]
    last_body = abs(closes[-1] - opens[-1])
    doji_last = 1.0 if (last_range > 0 and last_body / last_range < 0.1) else 0.0

    # High-low range %
    high_low_range_pct = (
        (highs[-1] - lows[-1]) / closes[-1] * 100 if closes[-1] else 0.0
    )

    return {
        "body_size_mean": body_size_mean,
        "body_size_last": body_size_last,
        "upper_wick_mean": upper_wick_mean,
        "lower_wick_mean": lower_wick_mean,
        "close_above_open_pct": close_above_open_pct,
        "momentum_3": momentum_3,
        "momentum_10": momentum_10,
        "volume_trend": volume_trend,
        "engulfing_bullish": engulfing_bullish,
        "engulfing_bearish": engulfing_bearish,
        "doji_last": doji_last,
        "high_low_range_pct": high_low_range_pct,
    }
