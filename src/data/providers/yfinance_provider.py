"""
data.providers.yfinance_provider
==================================

YFinanceProvider — live delayed market data via the yfinance library.

Fetches the latest available price and volume for a symbol using
Yahoo Finance. No API key required. Data is typically 15-min delayed
for equities — suitable for paper trading validation.

Implements IDataProvider — drop-in replacement for MarketDataProvider.

Python Version: 3.11+
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar

from data.models.market_tick import MarketTick
from data.providers.i_data_provider import IDataProvider


class YFinanceProvider:
    """Live delayed market data provider backed by Yahoo Finance.

    Uses yfinance to fetch the most recent closing price and volume.
    Suitable for paper trading validation — not for low-latency trading.

    Usage::

        provider = YFinanceProvider()
        tick = provider.fetch("AAPL")
        print(tick.price, tick.volume)
    """

    SOURCE_NAME: ClassVar[str] = "yfinance"

    def __init__(self, period: str = "1d", interval: str = "1m") -> None:
        """
        Args:
            period:   How far back to look for the latest tick (default: 1d).
            interval: Candle interval — "1m", "5m", "1h", "1d" etc.
        """
        try:
            import yfinance as yf
            self._yf = yf
        except ImportError as exc:
            raise ImportError(
                "yfinance is required. Install it with: pip install yfinance"
            ) from exc

        self._period = period
        self._interval = interval

    # ------------------------------------------------------------------
    # IDataProvider implementation
    # ------------------------------------------------------------------

    @property
    def source_name(self) -> str:
        """Return the canonical provider name."""
        return self.SOURCE_NAME

    def fetch(self, symbol: str) -> MarketTick:
        """Fetch the latest available tick for a symbol from Yahoo Finance.

        Args:
            symbol: Canonical ticker (e.g. "AAPL", "BTC-USD", "MSFT").

        Returns:
            Immutable ``MarketTick`` with the most recent price and volume.

        Raises:
            ValueError: If the symbol is empty, not found, or has no data.
            RuntimeError: If the Yahoo Finance request fails.
        """
        if not symbol or not symbol.strip():
            raise ValueError("symbol must not be empty.")

        sym = symbol.strip().upper()

        try:
            ticker = self._yf.Ticker(sym)
            hist = ticker.history(period=self._period, interval=self._interval)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to fetch data for '{sym}' from Yahoo Finance: {exc}"
            ) from exc

        if hist is None or hist.empty:
            raise ValueError(
                f"No data returned for symbol '{sym}' from Yahoo Finance."
            )

        # Take the last available row
        latest = hist.iloc[-1]
        price = float(latest["Close"])
        volume = float(latest.get("Volume", 0.0))

        # Timestamp from the index
        raw_ts = hist.index[-1]
        try:
            ts = raw_ts.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            ts = datetime.now(timezone.utc)

        return MarketTick(
            symbol=sym,
            price=price,
            volume=volume,
            timestamp=ts,
            source=self.SOURCE_NAME,
        )


# Runtime protocol check
assert isinstance(YFinanceProvider.__new__(YFinanceProvider), IDataProvider), (
    "YFinanceProvider does not satisfy the IDataProvider Protocol."
)
