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

import logging
import time
from datetime import datetime, timezone
from typing import ClassVar

_log = logging.getLogger(__name__)

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
    _HISTORY_LEN: ClassVar[int] = 5

    def __init__(
        self,
        symbols: list[str] | None = None,
        ttl_seconds: float = 60.0,
        period: str = "1d",
        interval: str = "1m",
        use_tor: bool = False,
        tor_control_password: str = "",
    ) -> None:
        """
        Args:
            symbols:              Known symbols to pre-warm cache for.
            ttl_seconds:          How long a cached price is considered fresh.
            period:               History window passed to yfinance.
            interval:             Candle interval (e.g. "1m", "5m").
            use_tor:              Route all requests through local Tor proxy.
                                  Requires Tor daemon on 127.0.0.1:9050.
            tor_control_password: Tor control port password (default empty).
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
        # Real recent-history cache (most recent last), populated alongside
        # the single-price cache above. Used by fetch_recent() so callers
        # never have to fabricate synthetic ticks.
        self._recent_cache: dict[str, list[MarketTick]] = {}

        # Tor proxy setup — only imported when use_tor=True
        self._tor = None
        if use_tor:
            import os
            from data.providers.tor_session import TorProxySession
            self._tor = TorProxySession(control_password=tor_control_password)
            # Set env-level proxy so yfinance's internal requests picks it up
            os.environ["HTTP_PROXY"] = "socks5h://127.0.0.1:9150"
            os.environ["HTTPS_PROXY"] = "socks5h://127.0.0.1:9150"
            _log.info("Tor proxy set via environment variables (port 9150).")

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

    def fetch_recent(self, symbol: str, n: int = 5) -> list[MarketTick]:
        """Return up to the last ``n`` real MarketTicks for a symbol.

        Unlike ``fetch``, which only returns the latest price, this
        returns genuine recent history pulled from the same batch
        request — never fabricated or synthetically perturbed data.
        Most recent tick is last.

        Args:
            symbol: Canonical ticker symbol.
            n:      Number of recent ticks requested.

        Returns:
            Up to ``n`` real ``MarketTick`` objects, oldest first. If
            fewer than ``n`` real observations are available (e.g. thin
            trading or a fresh cache), the earliest real tick is repeated
            to pad the window rather than inventing prices.

        Raises:
            ValueError: If symbol is empty or no data is available at all.
        """
        if not symbol or not symbol.strip():
            raise ValueError("symbol must not be empty.")

        sym = symbol.strip().upper()
        recent = self._recent_cache.get(sym)

        if not recent:
            self._fetch_batch([sym])
            recent = self._recent_cache.get(sym)

        if not recent:
            # No history array available (e.g. sparse Tor response) —
            # fall back to the single latest real tick, padded, rather
            # than raising or fabricating synthetic prices.
            latest = self.fetch(sym)
            return [latest] * n

        if len(recent) < n:
            pad = [recent[0]] * (n - len(recent))
            recent = pad + recent

        return recent[-n:]

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
        """Fetch prices for symbols, using Tor session if available.

        When Tor is active, fetches directly via Yahoo Finance JSON API
        through the Tor SOCKS5 proxy (bypasses yfinance's internal client).
        Falls back to yf.download when Tor is not configured.

        Args:
            symbols: List of ticker symbols to fetch.
        """
        if self._tor is not None:
            self._fetch_via_tor(symbols)
        else:
            self._fetch_via_yfinance(symbols)

    def _fetch_via_tor(self, symbols: list[str]) -> None:
        """Fetch prices via Yahoo Finance JSON API through Tor session."""
        now_epoch = time.monotonic()
        now_dt = datetime.now(timezone.utc)
        session = self._tor.session
        for sym in symbols:
            for attempt in range(self._MAX_RETRIES):
                try:
                    url = (
                        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
                        f"?interval=1m&range=1d"
                    )
                    resp = session.get(url, timeout=15, headers={
                        "User-Agent": "Mozilla/5.0"
                    })
                    if resp.status_code == 429:
                        self._tor.rotate_ip()
                        time.sleep(10)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    result = data["chart"]["result"][0]
                    timestamps = result.get("timestamp", [])
                    closes = result["indicators"]["quote"][0]["close"]
                    volumes = result["indicators"]["quote"][0].get("volume", [0] * len(closes))
                    price = float(next(v for v in reversed(closes) if v is not None))
                    volume = float(next((v for v in reversed(volumes) if v is not None), 0.0))
                    self._cache[sym] = (price, volume, now_dt, now_epoch)

                    # Keep the real recent bars (not just the last one) so
                    # callers can build a genuine lookback window instead of
                    # fabricating synthetic ticks.
                    recent: list[MarketTick] = []
                    for i in range(len(closes)):
                        c = closes[i]
                        if c is None:
                            continue
                        v = volumes[i] if i < len(volumes) and volumes[i] is not None else 0.0
                        ts = (
                            datetime.fromtimestamp(timestamps[i], tz=timezone.utc)
                            if i < len(timestamps) and timestamps[i] is not None
                            else now_dt
                        )
                        recent.append(
                            MarketTick(
                                symbol=sym, price=float(c), volume=float(v),
                                timestamp=ts, source=self.SOURCE_NAME,
                            )
                        )
                    if recent:
                        self._recent_cache[sym] = recent[-self._HISTORY_LEN:]
                    break
                except Exception:
                    _log.warning("Tor fetch failed for %s (attempt %d)", sym, attempt + 1, exc_info=True)
                    if attempt < self._MAX_RETRIES - 1:
                        self._tor.rotate_ip()
                        time.sleep(10)

    def _fetch_via_yfinance(self, symbols: list[str]) -> None:
        """Batch download via yf.download with exponential backoff."""
        tickers = " ".join(symbols)
        delay = 2.0
        for attempt in range(self._MAX_RETRIES):
            try:
                data = self._yf.download(
                    tickers=tickers,
                    period=self._period,
                    interval=self._interval,
                    group_by="ticker",
                    auto_adjust=True,
                    progress=False,
                    threads=False,
                )
                if data is None or data.empty:
                    return
                now_epoch = time.monotonic()
                if len(symbols) == 1:
                    self._store_single(symbols[0], data, now_epoch)
                else:
                    for sym in symbols:
                        try:
                            self._store_single(sym.upper(), data[sym.upper()], now_epoch)
                        except (KeyError, TypeError):
                            continue
                return
            except Exception as exc:
                err_str = str(exc).lower()
                is_rate_limit = "too many requests" in err_str or "429" in err_str
                if is_rate_limit and attempt < self._MAX_RETRIES - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
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

            # Keep real recent bars for fetch_recent(), not just the last row.
            recent: list[MarketTick] = []
            for _, row in df.tail(self._HISTORY_LEN).iterrows():
                try:
                    row_ts = row.name.to_pydatetime()
                    if row_ts.tzinfo is None:
                        row_ts = row_ts.replace(tzinfo=timezone.utc)
                    recent.append(
                        MarketTick(
                            symbol=symbol,
                            price=float(row["Close"]),
                            volume=float(row.get("Volume", 0.0)),
                            timestamp=row_ts,
                            source=self.SOURCE_NAME,
                        )
                    )
                except Exception:
                    continue
            if recent:
                self._recent_cache[symbol] = recent
        except Exception:
            _log.warning(
                "Failed to parse yfinance data for symbol '%s'",
                symbol,
                exc_info=True,
            )


# Runtime protocol check
assert isinstance(YFinanceProvider.__new__(YFinanceProvider), IDataProvider), (
    "YFinanceProvider does not satisfy the IDataProvider Protocol."
)
