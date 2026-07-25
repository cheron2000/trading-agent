"""
data.providers.av_news_provider
=================================

AVNewsProvider — fetches news sentiment from Alpha Vantage NEWS_SENTIMENT endpoint.

Rotates through all provided API keys one-per-cycle to spread the daily
request budget evenly across keys.

Free tier: 25 req/day per key. With 4 keys = 100 news fetches/day.
Fetch news every N cycles per symbol to stay within budget.

Usage::

    news = AVNewsProvider(api_keys=["KEY1","KEY2","KEY3","KEY4"])
    headlines = news.fetch_sentiment("AAPL")
    # Returns list of dicts: [{title, sentiment_label, sentiment_score}, ...]

Python Version: 3.11+
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

_log = logging.getLogger(__name__)

_BASE_URL = "https://www.alphavantage.co/query"
_RATE_LIMIT_SLEEP = 12.0  # 5 req/min → 12s between calls


class AVNewsProvider:
    """Fetches news sentiment from Alpha Vantage, rotating keys each cycle.

    Key rotation strategy: one key per cycle (not per request).
    With 4 keys and 60 cycles/hour, each key handles 15 cycles = 15 requests/hour.
    Well within the 25/day free tier limit per key.
    """

    def __init__(
        self,
        api_keys: list[str],
        max_articles: int = 5,
        cache_ttl: float = 300.0,  # 5 min cache — news doesn't change that fast
    ) -> None:
        """
        Args:
            api_keys:     List of AV API keys. Rotated per cycle.
            max_articles: Max headlines to return per symbol.
            cache_ttl:    Seconds to cache news before re-fetching.
        """
        if not api_keys:
            raise ValueError("api_keys must not be empty.")
        self._keys = [k.strip() for k in api_keys if k.strip()]
        self._max_articles = max_articles
        self._cache_ttl = cache_ttl

        # Current key index — advances each call to next_key()
        self._key_index: int = 0
        self._last_request_at: float = 0.0

        # Cache: symbol → (headlines_list, fetched_at_monotonic)
        self._cache: dict[str, tuple[list[dict], float]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def advance_key(self) -> None:
        """Rotate to next API key. Call once per trading cycle."""
        self._key_index = (self._key_index + 1) % len(self._keys)
        _log.debug("News key rotated → key %d/%d", self._key_index + 1, len(self._keys))

    @property
    def current_key_index(self) -> int:
        return self._key_index

    def fetch_sentiment(self, symbol: str) -> list[dict]:
        """Fetch latest news sentiment for a symbol.

        Returns cached result if within cache_ttl.

        Args:
            symbol: Ticker symbol (e.g. "AAPL").

        Returns:
            List of article dicts, each with:
              - title: str
              - sentiment_label: "Bullish" | "Bearish" | "Neutral" | "Somewhat-Bullish" | "Somewhat-Bearish"
              - sentiment_score: float (-1.0 to 1.0)
              - source: str
              - time_published: str
            Empty list on any error.
        """
        sym = symbol.strip().upper()

        # Return cached if fresh
        cached = self._cache.get(sym)
        if cached is not None:
            headlines, fetched_at = cached
            if time.monotonic() - fetched_at < self._cache_ttl:
                return headlines

        try:
            headlines = self._fetch_from_av(sym)
            self._cache[sym] = (headlines, time.monotonic())
            return headlines
        except Exception as exc:
            _log.warning("News fetch failed for %s: %s", sym, exc)
            # Return stale cache if available, else empty
            if cached:
                return cached[0]
            return []

    def format_for_prompt(self, symbol: str) -> str:
        """Return a compact news summary string for LLM prompt injection.

        Args:
            symbol: Ticker symbol.

        Returns:
            Multi-line string summarising recent news sentiment.
            Empty string if no news available.
        """
        headlines = self.fetch_sentiment(symbol)
        if not headlines:
            return ""

        lines = [f"Recent news for {symbol} ({len(headlines)} articles):"]
        for h in headlines[:self._max_articles]:
            label = h.get("sentiment_label", "Neutral")
            score = h.get("sentiment_score", 0.0)
            title = h.get("title", "")[:80]  # truncate long titles
            lines.append(f"  [{label} {score:+.2f}] {title}")

        # Overall sentiment summary
        scores = [h.get("sentiment_score", 0.0) for h in headlines]
        avg = sum(scores) / len(scores) if scores else 0.0
        overall = "Bullish" if avg > 0.15 else "Bearish" if avg < -0.15 else "Neutral"
        lines.append(f"  Overall sentiment: {overall} (avg score: {avg:+.3f})")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal fetch
    # ------------------------------------------------------------------

    def _fetch_from_av(self, symbol: str) -> list[dict]:
        """Hit the AV NEWS_SENTIMENT endpoint and parse results."""
        api_key = self._keys[self._key_index]

        # Respect per-minute rate limit
        elapsed = time.monotonic() - self._last_request_at
        if self._last_request_at > 0 and elapsed < _RATE_LIMIT_SLEEP:
            time.sleep(_RATE_LIMIT_SLEEP - elapsed)

        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": symbol,
            "limit": str(self._max_articles),
            "apikey": api_key,
        }
        url = f"{_BASE_URL}?{urlencode(params)}"

        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({})  # bypass Tor/system proxy
        )

        try:
            with opener.open(url, timeout=15) as resp:
                self._last_request_at = time.monotonic()
                data = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            self._last_request_at = time.monotonic()
            raise RuntimeError(f"AV news HTTP {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise RuntimeError(f"AV news network error: {exc}") from exc

        # Check AV error responses
        if "Note" in data or "Information" in data:
            msg = data.get("Note") or data.get("Information", "")
            raise RuntimeError(f"AV news rate limit/info: {msg[:100]}")

        feed = data.get("feed", [])
        if not feed:
            return []

        articles = []
        for item in feed[:self._max_articles]:
            # Find ticker-specific sentiment
            ticker_sentiments = item.get("ticker_sentiment", [])
            ticker_score = 0.0
            ticker_label = "Neutral"
            for ts in ticker_sentiments:
                if ts.get("ticker", "").upper() == symbol:
                    try:
                        ticker_score = float(ts.get("ticker_sentiment_score", 0.0))
                        ticker_label = ts.get("ticker_sentiment_label", "Neutral")
                    except (ValueError, TypeError):
                        pass
                    break

            articles.append({
                "title": item.get("title", ""),
                "source": item.get("source", ""),
                "time_published": item.get("time_published", ""),
                "sentiment_label": ticker_label,
                "sentiment_score": ticker_score,
            })

        _log.info("News fetched for %s — %d articles (key %d/%d)",
                  symbol, len(articles), self._key_index + 1, len(self._keys))
        return articles
