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

from data.models.market_tick import MarketTick
from data.providers.i_data_provider import IDataProvider

_log = logging.getLogger(__name__)

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
            raise ImportError("yfinance is required: pip install yfinance") from exc

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
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from data.providers.tor_session import (
                TorProxySession as TorProxySessionType,
            )

        self._tor: "TorProxySessionType | None" = None
        if use_tor:
            import os
            from data.providers.tor_session import TorProxySession

            # Port 9150 = Tor Browser (Windows), 9050 = tor daemon (Linux/EC2)
            _socks_port = int(os.environ.get("TOR_SOCKS_PORT", "9150"))
            _ctrl_port = int(os.environ.get("TOR_CONTROL_PORT", "9151"))
            self._tor = TorProxySession(
                control_password=tor_control_password,
                socks_port=_socks_port,
                control_port=_ctrl_port,
            )
            _log.info("Tor proxy active on SOCKS port %d.", _socks_port)

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
            raise ValueError(f"No data available for symbol '{sym}'.")

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

        Deliberately does NOT pad short windows with duplicated ticks:
        if fewer than ``n`` real observations exist, fewer are returned.
        This lets FeatureEngineer's source_quality (len(ticks)/window_size)
        genuinely reflect thin data instead of always reporting 1.0.

        Args:
            symbol: Canonical ticker symbol.
            n:      Maximum number of recent ticks requested.

        Returns:
            Up to ``n`` real ``MarketTick`` objects, oldest first, and
            never fewer than 1.

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
            # fall back to the single latest real tick rather than
            # raising or fabricating synthetic prices.
            return [self.fetch(sym)]

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
        through the Tor SOCKS5 proxy. If all Tor attempts fail, falls
        back to direct yfinance (no proxy) so the system keeps running.

        Args:
            symbols: List of ticker symbols to fetch.
        """
        if self._tor is not None:
            self._fetch_via_tor(symbols)
            # Check if Tor fetch succeeded for all symbols
            missing = [s for s in symbols if s.upper() not in self._cache]
            if missing:
                _log.warning(
                    "Tor fetch failed for %s — falling back to direct yfinance.",
                    missing,
                )
                self._fetch_via_yfinance(missing)
        else:
            self._fetch_via_yfinance(symbols)

    def _fetch_via_tor(self, symbols: list[str]) -> None:
        """Fetch prices via Yahoo Finance JSON API through Tor session."""
        if self._tor is None:
            return
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
                    resp = session.get(
                        url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}
                    )
                    if resp.status_code == 429:
                        if self._tor is not None:
                            try:
                                self._tor.rotate_ip()
                            except Exception:
                                pass
                        time.sleep(10)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    result = data["chart"]["result"][0]
                    timestamps = result.get("timestamp", [])
                    quote_data = result["indicators"]["quote"][0]
                    closes = quote_data.get("close") or []
                    volumes = quote_data.get("volume") or [0] * len(closes)
                    # Filter out None values (common pre-market / crypto gaps)
                    valid_closes = [v for v in closes if v is not None]
                    if not valid_closes:
                        raise ValueError(f"No valid close prices in response for {sym}")
                    price = float(valid_closes[-1])
                    volume = float(
                        next((v for v in reversed(volumes) if v is not None), 0.0)
                    )
                    self._cache[sym] = (price, volume, now_dt, now_epoch)

                    # Keep the real recent bars (not just the last one) so
                    # callers can build a genuine lookback window instead of
                    # fabricating synthetic ticks.
                    recent: list[MarketTick] = []
                    for i in range(len(closes)):
                        c = closes[i]
                        if c is None:
                            continue
                        v = (
                            volumes[i]
                            if i < len(volumes) and volumes[i] is not None
                            else 0.0
                        )
                        ts = (
                            datetime.fromtimestamp(timestamps[i], tz=timezone.utc)
                            if i < len(timestamps) and timestamps[i] is not None
                            else now_dt
                        )
                        recent.append(
                            MarketTick(
                                symbol=sym,
                                price=float(c),
                                volume=float(v),
                                timestamp=ts,
                                source=self.SOURCE_NAME,
                            )
                        )
                    if recent:
                        self._recent_cache[sym] = recent[-self._HISTORY_LEN :]
                    break
                except Exception as exc:
                    _log.warning(
                        "Tor fetch failed for %s (attempt %d): %s",
                        sym,
                        attempt + 1,
                        exc,
                    )
                    if attempt < self._MAX_RETRIES - 1:
                        if self._tor is not None:
                            try:
                                self._tor.rotate_ip()
                            except Exception:
                                pass
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
                            self._store_single(
                                sym.upper(), data[sym.upper()], now_epoch
                            )
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

            import pandas as pd

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            last = df.iloc[-1]
            close_col = [c for c in df.columns if str(c).lower() == "close"]
            vol_col = [c for c in df.columns if str(c).lower() == "volume"]

            price = float(last[close_col[0]]) if close_col else float(last.iloc[0])
            volume = float(last[vol_col[0]]) if vol_col else 0.0

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
                    r_price = (
                        float(row[close_col[0]]) if close_col else float(row.iloc[0])
                    )
                    r_vol = float(row[vol_col[0]]) if vol_col else 0.0
                    recent.append(
                        MarketTick(
                            symbol=symbol,
                            price=r_price,
                            volume=r_vol,
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
assert isinstance(
    YFinanceProvider.__new__(YFinanceProvider), IDataProvider
), "YFinanceProvider does not satisfy the IDataProvider Protocol."
