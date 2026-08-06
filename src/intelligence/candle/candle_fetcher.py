"""
intelligence.candle.candle_fetcher
=====================================
Fetches last N OHLCV candles for a symbol via yfinance.
Self-caching with configurable TTL. No project layer imports.
"""

from __future__ import annotations

import logging
import time

_log = logging.getLogger(__name__)


class CandleFetcher:
    """Fetch OHLCV candle history with per-symbol TTL cache."""

    def __init__(
        self,
        interval: str = "5m",
        n_candles: int = 50,
        ttl_seconds: float = 600.0,
    ) -> None:
        self._interval = interval
        self._n_candles = n_candles
        self._ttl = ttl_seconds
        # symbol -> (candles, fetched_at_monotonic)
        self._cache: dict[str, tuple[list[dict], float]] = {}

    def fetch(self, symbol: str) -> list[dict]:
        """Return up to n_candles OHLCV dicts for symbol.

        Uses cached result if within TTL. Returns [] on any error.
        Each dict has keys: open, high, low, close, volume, timestamp.
        """
        now = time.monotonic()
        cached = self._cache.get(symbol)
        if cached and (now - cached[1]) < self._ttl:
            return cached[0]

        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1d", interval=self._interval)
            if df is None or df.empty:
                _log.warning("CandleFetcher: empty result for %s", symbol)
                return []

            # Normalise column names (handle MultiIndex)
            import pandas as pd

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [str(c).lower() for c in df.columns]

            candles: list[dict] = []
            for ts, row in df.iterrows():
                candles.append(
                    {
                        "open": float(row.get("open", 0)),
                        "high": float(row.get("high", 0)),
                        "low": float(row.get("low", 0)),
                        "close": float(row.get("close", 0)),
                        "volume": float(row.get("volume", 0)),
                        "timestamp": str(ts),
                    }
                )

            candles = candles[-self._n_candles :]
            self._cache[symbol] = (candles, now)
            return candles

        except Exception as exc:
            _log.warning("CandleFetcher: error fetching %s — %s", symbol, exc)
            return []
