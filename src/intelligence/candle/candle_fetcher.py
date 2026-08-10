"""
intelligence.candle.candle_fetcher
=====================================
Fetches last N OHLCV candles for a symbol via Yahoo Finance JSON API
routed through Tor SOCKS5 proxy (port 9150). Self-caching with TTL.
No project layer imports.
"""

from __future__ import annotations

import logging
import time

_log = logging.getLogger(__name__)

_TOR_PROXY = "socks5h://127.0.0.1:9150"


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

        Routes through Tor SOCKS5 proxy to avoid rate limiting.
        Uses cached result if within TTL. Returns [] on any error.
        Each dict has keys: open, high, low, close, volume, timestamp.
        """
        now = time.monotonic()
        cached = self._cache.get(symbol)
        if cached and (now - cached[1]) < self._ttl:
            return cached[0]

        try:
            import requests

            session = requests.Session()
            session.proxies = {"http": _TOR_PROXY, "https": _TOR_PROXY}

            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
                f"?interval={self._interval}&range=5d"
            )
            resp = session.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            data = resp.json()

            result = data["chart"]["result"][0]
            timestamps = result.get("timestamp", [])
            q = result["indicators"]["quote"][0]
            opens = q.get("open", [])
            highs = q.get("high", [])
            lows = q.get("low", [])
            closes = q.get("close", [])
            volumes = q.get("volume", [])

            candles: list[dict] = []
            for i in range(len(closes)):
                if closes[i] is None or opens[i] is None:
                    continue
                candles.append(
                    {
                        "open": float(opens[i] or closes[i]),
                        "high": float(highs[i] or closes[i]),
                        "low": float(lows[i] or closes[i]),
                        "close": float(closes[i]),
                        "volume": float(volumes[i] or 0) if i < len(volumes) else 0.0,
                        "timestamp": (
                            str(timestamps[i]) if i < len(timestamps) else str(i)
                        ),
                    }
                )

            candles = candles[-self._n_candles :]
            self._cache[symbol] = (candles, now)
            return candles

        except Exception as exc:
            _log.warning("CandleFetcher: error fetching %s - %s", symbol, exc)
            return []
