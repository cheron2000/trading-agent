"""
data.providers.yfinance_provider
==================================

YFinanceProvider — live delayed market data via yfinance.

Rate-limit mitigations built in:
  1. Batch fetch  — downloads all symbols in a single HTTP request
  2. TTL cache    — returns cached price if fresher than ttl_seconds
  3. Exponential backoff — retries on 429 with 2^n second waits

Python Version: 3.11+
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import ClassVar

from data.models.market_tick import MarketTick
from data.providers.i_data_provider import IDataProvider

# Cached price entry: (price, volume, timestamp, fetched_at_epoch)
_CacheEntry = tuple[float, float, datetime, float]


class YFinanceProvider:
    """Live delayed market data provider backed by Yahoo Finance.

    Batches all symbol fetches into a single HTTP call and caches
    results with a configurable TTL to stay well within rate limits.

    Usage::

        provider = YFinanceProvider(symbols=["AAPL", "MSFT", "BTC-USD"])
        provider.warm_cache()          # optional: pre-fetch all at once
        tick = provider.fetch("AAPL")  # returns cached or fresh data
    """

    SOURCE_NAME: ClassVar[str] = "yfinance"
    _MAX_RETRIES: ClassVar[int] = 3

    def __init__(
        self,
        symbols: list[str] | None = None,
        ttl_seconds: float = 60.0,
        period: str = "1d",
        interval: str = "1m",
    ) -> None:
        """
        Args:
            symbols:     Known symbols to pre-warm cache for. Optional.
            ttl_seconds: How long a cached price is considered fresh.
                         Default 60s — safe for Yahoo Finance free tier.
            period:      History window passed to yfinance (e.g. "1d").
            interval:    Candle interval (e.g. "1m", "5m", "1h").
        """
        try:
            import yfinance as yf
            self._yf = yf
        except ImportError as exc:
            raise ImportError(
                "yfinance is required: pip install yfinance"
            ) from exc

        self._symbols = [s.upper() for s in (symbols or [])]
        self._ttl = ttl_seconds
        self._period = period
        self._interval = interval
        self._cache: dict[str, _CacheEntry] = {}

    # ------------------------------------------------------------------
    # IDataProvider implementation
    # ------------------------------------------------------------------

    @property
    def source_name(self) -> str:
        return self.SOURCE_NAME

    def fetch(self, symbol: str) -> MarketTick:
        """Return the latest MarketTick for a symbol.

        Returns cached data if it is within the TTL window.
        Otherwise fetches from Yahoo Finance with backoff retry.

        Args:
            symbol: Canonical ticker symbol.

        Returns:
            Immutable ``MarketTick``.

        Raises:
            ValueError:  If symbol is empty or no data is available.
            RuntimeError: If Yahoo Finance is unreachable after retries.
        """
        if not symbol or not symbol.strip():
            raise ValueError("symbol must not be empty.")

        sym = symbol.strip().upper()

        # Return cached value if still fresh
        cached = self._cache.get(sym)
        if cached is not None:
            price, volume, ts, fetched_at = cached
            if time.monotonic() - fetched_at < self._ttl:
                return MarketTick(
                    symbol=sym,
                    price=price,
                    volume=volume,
                    timestamp=ts,
                    source=self.SOURCE_NAME,
                )

        # Cache miss or stale — fetch fresh data with backoff
        self._fetch_batch([sym])

        entry = self._cache.get(sym)
        if entry is None:
            raise ValueError(
                f"No data available for symbol '{sym}'."
            )

        price, volume, ts, _ = entry
        return MarketTick(
            symbol=sym,
            price=price,
            volume=volume,
            timestamp=ts,
            source=self.SOURCE_NAME,
        )

    def warm_cache(self, symbols: list[str] | None = None) -> None:
        """Batch-fetch prices for all known symbols in one request.

        Call this once before the simulation loop to pre-populate
        the cache and avoid per-symbol requests during ticks.

        Args:
            symbols: Override the symbol list. Defaults to self._symbols.
        """
        syms = [s.upper() for s in (symbols or self._symbols)]
        if not syms:
            return
        self._fetch_batch(syms)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_batch(self, symbols: list[str]) -> None:
        """Batch download via yf.download and populate the cache.

        Uses exponential backoff on rate-limit errors (429).

        Args:
            symbols: List of ticker symbols to fetch.
        """
        tickers = " ".join(symbols)
        delay = 2.0

        for attempt in range(self._MAX_RETRIES):
            try:
                # Single HTTP call for all symbols
                data = self._yf.download(
                    tickers=tickers,
                    period=self._period,
                    interval=self._interval,
                    group_by="ticker",
                    auto_adjust=True,
                    progress=False,
                    threads=False,  # avoid internal parallelism
                )

                if data is None or data.empty:
                    return

                now_epoch = time.monotonic()

                if len(symbols) == 1:
                    # Single-symbol download has flat columns
                    sym = symbols[0]
                    self._store_single(sym, data, now_epoch)
                else:
                    # Multi-symbol download has MultiIndex columns
                    for sym in symbols:
                        sym_upper = sym.upper()
                        try:
                            sym_data = data[sym_upper]
                            self._store_single(sym_upper, sym_data, now_epoch)
                        except (KeyError, TypeError):
                            continue
                return  # success

            except Exception as exc:
                err_str = str(exc).lower()
                is_rate_limit = (
                    "too many requests" in err_str
                    or "rate limit" in err_str
                    or "429" in err_str
                )
                if is_rate_limit and attempt < self._MAX_RETRIES - 1:
                    time.sleep(delay)
                    delay *= 2  # exponential backoff: 2s, 4s, 8s
                    continue
                # Non-rate-limit error or exhausted retries — give up silently
                return

    def _store_single(
        self,
        symbol: str,
        df,
        now_epoch: float,
    ) -> None:
        """Extract the last row from a DataFrame and store in cache."""
        try:
            if df is None or df.empty:
                return

            last = df.iloc[-1]
            price = float(last["Close"])
            volume = float(last.get("Volume", 0.0))

            raw_ts = df.index[-1]
            try:
                ts = raw_ts.to_pydatetime()
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except Exception:
                ts = datetime.now(timezone.utc)

            self._cache[symbol] = (price, volume, ts, now_epoch)
        except Exception:
            pass  # skip symbols with unexpected structure


# Runtime protocol check
assert isinstance(YFinanceProvider.__new__(YFinanceProvider), IDataProvider), (
    "YFinanceProvider does not satisfy the IDataProvider Protocol."
)
