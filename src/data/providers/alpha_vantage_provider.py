"""
data.providers.alpha_vantage_provider
=======================================

AlphaVantageProvider — live delayed market data via Alpha Vantage REST API.

Features:
  - API key rotation array: automatically rotates to the next key after
    ``requests_per_key`` calls (default 25 — the free-tier daily limit).
  - TTL cache: skips a network call if the cached price is still fresh.
  - Graceful fallback: logs a warning and raises RuntimeError if all keys
    are exhausted rather than silently returning stale data.
  - Zero cross-layer imports: only uses Foundation models via IDataProvider.

Free-tier limits (as of 2024):
  - 25 requests / day per API key
  - 5 requests / minute per API key

Request budget per simulation run:
  - warm_cache() for N symbols = N requests (1 per symbol)
  - Each day × N symbols = N requests (TTL cache absorbs intra-day repeats)
  - 30-day run, 6 symbols: 6 + (6 × 30) = 186 requests total
  - Minimum keys for one 30-day run:  ceil(186 / 25) = 8 keys
  - Keys for 1 hour of continuous runs: ~15 keys

Usage::

    provider = AlphaVantageProvider(
        api_keys=["KEY1", "KEY2", "KEY3", ...],
        symbols=["AAPL", "MSFT", "BTC-USD"],
        requests_per_key=25,   # rotate after this many calls per key
        ttl_seconds=60.0,
    )
    provider.warm_cache()
    tick = provider.fetch("AAPL")

Python Version: 3.11+
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import ClassVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from data.models.market_tick import MarketTick
from data.providers.i_data_provider import IDataProvider

_log = logging.getLogger(__name__)

# Alpha Vantage base URL — no third-party HTTP client required
_BASE_URL = "https://www.alphavantage.co/query"

# Mapping of crypto base symbols to Alpha Vantage format
# AV uses "BTC" not "BTC-USD"; we strip the "-USD" suffix automatically
_CRYPTO_BASES = {"BTC", "ETH", "SOL", "DOGE", "ADA", "XRP", "BNB", "AVAX"}


class AlphaVantageProvider:
    """Live delayed market data via Alpha Vantage with API key rotation.

    Automatically rotates through a list of API keys, switching to the
    next key once ``requests_per_key`` calls have been made on the current
    key. This multiplies the effective daily request budget:

        total_daily_budget = len(api_keys) × requests_per_key

    TTL caching prevents redundant calls within the same simulation tick.
    """

    SOURCE_NAME: ClassVar[str] = "alphavantage"
    _RATE_LIMIT_SLEEP: ClassVar[float] = 12.0  # 5 req/min → 1 per 12s
    _MAX_RETRIES: ClassVar[int] = 3

    def __init__(
        self,
        api_keys: list[str],
        symbols: list[str] | None = None,
        requests_per_key: int = 25,
        ttl_seconds: float = 60.0,
        rate_limit_sleep: float = _RATE_LIMIT_SLEEP,
    ) -> None:
        """
        Args:
            api_keys:          List of Alpha Vantage API keys. Rotated
                               automatically after ``requests_per_key`` calls.
            symbols:           Known symbols for warm_cache(). Optional.
            requests_per_key:  Number of requests before rotating to next key.
                               Set to 25 for free-tier keys (daily limit).
            ttl_seconds:       Cache TTL — reuse cached price within this window.
            rate_limit_sleep:  Seconds to wait between requests to stay within
                               5 req/min. Default 12s.

        Raises:
            ValueError: If api_keys is empty or requests_per_key < 1.
        """
        if not api_keys:
            raise ValueError("api_keys must not be empty.")
        if requests_per_key < 1:
            raise ValueError("requests_per_key must be >= 1.")

        self._keys = [k.strip() for k in api_keys if k and k.strip()]
        if not self._keys:
            raise ValueError("api_keys contains no valid (non-empty) keys.")

        self._requests_per_key = requests_per_key
        self._ttl = ttl_seconds
        self._rate_limit_sleep = rate_limit_sleep
        self._symbols = [s.upper() for s in (symbols or [])]

        # Key rotation state
        self._key_index: int = 0
        self._key_request_count: int = 0  # requests made on current key

        # Cache: symbol → (price, volume, timestamp, fetched_at_monotonic)
        self._cache: dict[str, tuple[float, float, datetime, float]] = {}

        # Per-minute rate limiter: track last request time
        self._last_request_at: float = 0.0

        total_budget = len(self._keys) * self._requests_per_key
        _log.info(
            "AlphaVantageProvider ready — %d key(s), %d req/key, "
            "total daily budget: %d requests.",
            len(self._keys),
            self._requests_per_key,
            total_budget,
        )

    # ------------------------------------------------------------------
    # IDataProvider implementation
    # ------------------------------------------------------------------

    @property
    def source_name(self) -> str:
        return self.SOURCE_NAME

    def fetch(self, symbol: str) -> MarketTick:
        """Return the latest MarketTick for a symbol.

        Returns cached data if within TTL. Otherwise fetches from
        Alpha Vantage, rotating API keys as needed.

        Args:
            symbol: Canonical ticker (e.g. "AAPL", "BTC-USD").

        Returns:
            Immutable ``MarketTick``.

        Raises:
            ValueError:  If symbol is empty.
            RuntimeError: If all API keys are exhausted or unreachable.
        """
        if not symbol or not symbol.strip():
            raise ValueError("symbol must not be empty.")

        sym = symbol.strip().upper()

        # Return cached value if still fresh
        cached = self._cache.get(sym)
        if cached is not None:
            price, volume, ts, fetched_at = cached
            if time.monotonic() - fetched_at < self._ttl:
                _log.debug(
                    "Cache hit for %s (%.1fs old).", sym, time.monotonic() - fetched_at
                )
                return MarketTick(
                    symbol=sym,
                    price=price,
                    volume=volume,
                    timestamp=ts,
                    source=self.SOURCE_NAME,
                )

        # Cache miss — fetch from Alpha Vantage
        self._fetch_symbol(sym)

        entry = self._cache.get(sym)
        if entry is None:
            raise RuntimeError(
                f"No data returned from Alpha Vantage for '{sym}'. "
                "Check symbol name and API key validity."
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
        """Pre-fetch prices for all known symbols.

        Respects the rate limit sleep between each symbol to stay within
        5 requests/minute. Call once before the simulation loop.

        Args:
            symbols: Override the symbol list. Defaults to self._symbols.
        """
        syms = [s.upper() for s in (symbols or self._symbols)]
        if not syms:
            _log.warning("warm_cache called with no symbols — nothing to fetch.")
            return

        _log.info("Warming cache for %d symbol(s): %s", len(syms), syms)
        for i, sym in enumerate(syms):
            # Sleep BEFORE each request (except the first) to stay within 5 req/min
            if i > 0:
                _log.debug(
                    "Rate limit sleep %.1fs before fetching %s",
                    self._rate_limit_sleep,
                    sym,
                )
                time.sleep(self._rate_limit_sleep)
            try:
                self._fetch_symbol(sym)
                _log.info(
                    "  [%d/%d] %s — cached @ $%.4f.",
                    i + 1,
                    len(syms),
                    sym,
                    self._cache[sym][0] if sym in self._cache else 0,
                )
            except Exception as exc:  # noqa: BLE001 -- 3rd-party errors vary; logged
                _log.warning("  [%d/%d] %s — failed: %s", i + 1, len(syms), sym, exc)

    # ------------------------------------------------------------------
    # Key rotation
    # ------------------------------------------------------------------

    @property
    def current_key(self) -> str:
        """Return the currently active API key."""
        return self._keys[self._key_index]

    @property
    def keys_remaining(self) -> int:
        """Number of keys not yet exhausted (including current)."""
        return len(self._keys) - self._key_index

    @property
    def requests_used_on_current_key(self) -> int:
        """Requests made on the current key."""
        return self._key_request_count

    @property
    def total_budget_remaining(self) -> int:
        """Estimated remaining requests across all remaining keys."""
        current_remaining = self._requests_per_key - self._key_request_count
        future_keys = len(self._keys) - self._key_index - 1
        return current_remaining + future_keys * self._requests_per_key

    def _rotate_key(self) -> bool:
        """Advance to the next API key.

        Returns:
            True if a new key is available, False if all keys exhausted.
        """
        if self._key_index + 1 >= len(self._keys):
            return False
        self._key_index += 1
        self._key_request_count = 0
        _log.info(
            "API key rotated → key %d/%d. Budget remaining: ~%d requests.",
            self._key_index + 1,
            len(self._keys),
            self.total_budget_remaining,
        )
        return True

    def _consume_request(self) -> None:
        """Increment request counter; rotate key if limit reached."""
        self._key_request_count += 1
        if self._key_request_count >= self._requests_per_key:
            rotated = self._rotate_key()
            if not rotated:
                _log.error(
                    "All %d API key(s) exhausted (each had %d requests). "
                    "Add more keys or wait for daily reset.",
                    len(self._keys),
                    self._requests_per_key,
                )

    # ------------------------------------------------------------------
    # Alpha Vantage fetch logic
    # ------------------------------------------------------------------

    def _fetch_symbol(self, symbol: str) -> None:
        """Fetch latest quote for symbol and store in cache.

        Determines whether to use the GLOBAL_QUOTE (equities) or
        CURRENCY_EXCHANGE_RATE (crypto) endpoint automatically.

        Raises:
            RuntimeError: If all keys exhausted or network unreachable.
        """
        is_crypto = self._is_crypto(symbol)

        for attempt in range(self._MAX_RETRIES):
            if self._key_index >= len(self._keys):
                raise RuntimeError(
                    f"All Alpha Vantage API keys exhausted. Cannot fetch '{symbol}'."
                )

            api_key = self.current_key

            try:
                if is_crypto:
                    price, volume, ts = self._fetch_crypto(symbol, api_key)
                else:
                    price, volume, ts = self._fetch_equity(symbol, api_key)

                self._consume_request()
                self._cache[symbol] = (price, volume, ts, time.monotonic())
                _log.debug(
                    "Fetched %s → $%.4f (key %d, req %d/%d)",
                    symbol,
                    price,
                    self._key_index + 1,
                    self._key_request_count,
                    self._requests_per_key,
                )
                return

            except _RateLimitError:
                _log.warning(
                    "Rate limit hit on key %d — rotating key (attempt %d/%d).",
                    self._key_index + 1,
                    attempt + 1,
                    self._MAX_RETRIES,
                )
                if not self._rotate_key():
                    raise RuntimeError(
                        f"Rate limited and all API keys exhausted for '{symbol}'."
                    )
                time.sleep(1.0)  # brief pause before retrying with new key

            except _KeyInvalidError:
                _log.warning("Invalid API key at index %d — rotating.", self._key_index)
                if not self._rotate_key():
                    raise RuntimeError(
                        f"All API keys invalid or exhausted for '{symbol}'."
                    )

            except Exception as exc:
                if attempt < self._MAX_RETRIES - 1:
                    wait = 2.0**attempt
                    _log.warning(
                        "Fetch attempt %d failed for '%s': %s. Retrying in %.0fs.",
                        attempt + 1,
                        symbol,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"Failed to fetch '{symbol}' after {self._MAX_RETRIES} attempts: {exc}"
                    ) from exc

    def _fetch_equity(self, symbol: str, api_key: str) -> tuple[float, float, datetime]:
        """Fetch equity quote via GLOBAL_QUOTE endpoint."""
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
            "apikey": api_key,
        }
        data = self._http_get(params)

        # Check for API-level errors
        self._check_av_errors(data, symbol)

        quote = data.get("Global Quote", {})
        if not quote:
            raise RuntimeError(
                f"Empty Global Quote response for '{symbol}'. "
                "Symbol may be invalid or delisted."
            )

        try:
            price = float(quote["05. price"])
            volume = float(quote.get("06. volume", 0.0))
            date_str = quote.get("07. latest trading day", "")
            ts = self._parse_date(date_str)
        except (KeyError, ValueError) as exc:
            raise RuntimeError(
                f"Unexpected Global Quote format for '{symbol}': {exc}"
            ) from exc

        return price, volume, ts

    def _fetch_crypto(self, symbol: str, api_key: str) -> tuple[float, float, datetime]:
        """Fetch crypto quote via CURRENCY_EXCHANGE_RATE endpoint.

        Strips '-USD' suffix automatically (e.g. 'BTC-USD' → 'BTC').
        """
        base = symbol.split("-")[0]  # "BTC-USD" → "BTC"
        params = {
            "function": "CURRENCY_EXCHANGE_RATE",
            "from_currency": base,
            "to_currency": "USD",
            "apikey": api_key,
        }
        data = self._http_get(params)

        self._check_av_errors(data, symbol)

        rate_info = data.get("Realtime Currency Exchange Rate", {})
        if not rate_info:
            raise RuntimeError(
                f"Empty exchange rate response for '{symbol}'. "
                "Check that '{base}' is a valid Alpha Vantage crypto symbol."
            )

        try:
            price = float(rate_info["5. Exchange Rate"])
            ts_str = rate_info.get("6. Last Refreshed", "")
            ts = self._parse_datetime(ts_str)
        except (KeyError, ValueError) as exc:
            raise RuntimeError(
                f"Unexpected exchange rate format for '{symbol}': {exc}"
            ) from exc

        # Crypto endpoint doesn't provide volume — use 0.0
        return price, 0.0, ts

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    def _http_get(self, params: dict) -> dict:
        """Make a GET request to Alpha Vantage and return parsed JSON.

        Enforces a minimum gap between requests to respect the 5 req/min
        per-minute rate limit (12s between calls).
        """
        # Enforce per-minute rate limit: wait if last request was < rate_limit_sleep ago
        elapsed = time.monotonic() - self._last_request_at
        if self._last_request_at > 0 and elapsed < self._rate_limit_sleep:
            wait = self._rate_limit_sleep - elapsed
            _log.debug("Rate limit guard: sleeping %.1fs", wait)
            time.sleep(wait)

        url = f"{_BASE_URL}?{urlencode(params)}"
        try:
            with urlopen(url, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
                self._last_request_at = time.monotonic()
                return json.loads(raw)
        except HTTPError as exc:
            self._last_request_at = time.monotonic()
            if exc.code == 429:
                raise _RateLimitError("HTTP 429 Too Many Requests") from exc
            raise
        except URLError as exc:
            raise RuntimeError(f"Network error reaching Alpha Vantage: {exc}") from exc

    # ------------------------------------------------------------------
    # Response validation
    # ------------------------------------------------------------------

    @staticmethod
    def _check_av_errors(data: dict, symbol: str) -> None:
        """Raise appropriate exception for Alpha Vantage API error responses."""
        # Rate limit message (daily or per-minute)
        note = data.get("Note", "")
        if note:
            raise _RateLimitError(note)

        # Information field — only raise on clear key/subscription issues
        info = data.get("Information", "")
        if info:
            info_lower = info.lower()
            if "invalid api key" in info_lower or "invalid api call" in info_lower:
                raise _KeyInvalidError(info)
            # Other Information messages are usually rate limit notices
            raise _RateLimitError(info)

        # Explicit error field
        if "Error Message" in data:
            raise RuntimeError(
                f"Alpha Vantage error for '{symbol}': {data['Error Message']}"
            )

    # ------------------------------------------------------------------
    # Symbol classification
    # ------------------------------------------------------------------

    @staticmethod
    def _is_crypto(symbol: str) -> bool:
        """Return True if symbol is a crypto pair (e.g. 'BTC-USD')."""
        base = symbol.split("-")[0].upper()
        return base in _CRYPTO_BASES or "-" in symbol

    # ------------------------------------------------------------------
    # Timestamp parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        """Parse 'YYYY-MM-DD' into UTC-aware datetime."""
        try:
            dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")  # noqa: DTZ007
            return dt.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            return datetime.now(timezone.utc)

    @staticmethod
    def _parse_datetime(dt_str: str) -> datetime:
        """Parse Alpha Vantage datetime string into UTC-aware datetime."""
        try:
            fmt = "%Y-%m-%d %H:%M:%S"
            dt = datetime.strptime(dt_str.strip()[:19], fmt)  # noqa: DTZ007
            return dt.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            return datetime.now(timezone.utc)


# ------------------------------------------------------------------
# Internal sentinel exceptions (not part of public API)
# ------------------------------------------------------------------


class _RateLimitError(Exception):
    """Raised when Alpha Vantage signals a rate limit (Note / 429)."""


class _KeyInvalidError(Exception):
    """Raised when an API key is invalid or lacks required permissions."""


# Runtime protocol check
assert isinstance(
    AlphaVantageProvider.__new__(AlphaVantageProvider), IDataProvider
), "AlphaVantageProvider does not satisfy the IDataProvider Protocol."
