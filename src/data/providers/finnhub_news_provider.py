"""
data.providers.finnhub_news_provider
======================================

FinnhubNewsProvider — company news from Finnhub.io free tier.

Free tier limits:
  - 60 requests / minute
  - No daily limit

With 4 symbols, 5-min cache: ~0.8 req/min — far under the 60 req/min cap.
No key rotation needed. One key handles everything.

Get a free key at: https://finnhub.io/register

Python Version: 3.11+
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

_log = logging.getLogger(__name__)

_BASE_URL = "https://finnhub.io/api/v1/company-news"

# Simple sentiment scoring based on keywords in headline
_BULLISH_WORDS = {
    "beat",
    "beats",
    "surge",
    "surges",
    "record",
    "profit",
    "growth",
    "upgrade",
    "buy",
    "strong",
    "bullish",
    "rally",
    "gains",
    "positive",
    "exceeds",
    "outperform",
    "raises",
    "boost",
    "soars",
}
_BEARISH_WORDS = {
    "miss",
    "misses",
    "fall",
    "falls",
    "loss",
    "losses",
    "decline",
    "downgrade",
    "sell",
    "weak",
    "bearish",
    "drop",
    "drops",
    "negative",
    "disappoints",
    "underperform",
    "cuts",
    "layoffs",
    "warns",
    "crash",
}


def _score_headline(headline: str) -> tuple[float, str]:
    """Simple keyword-based sentiment scoring.

    Returns (score, label) where score is -1.0 to +1.0.
    """
    words = set(headline.lower().split())
    bull = len(words & _BULLISH_WORDS)
    bear = len(words & _BEARISH_WORDS)

    if bull == 0 and bear == 0:
        return 0.0, "Neutral"
    total = bull + bear
    score = (bull - bear) / total

    if score > 0.3:
        label = "Bullish"
    elif score > 0.0:
        label = "Somewhat-Bullish"
    elif score < -0.3:
        label = "Bearish"
    elif score < 0.0:
        label = "Somewhat-Bearish"
    else:
        label = "Neutral"

    return round(score, 3), label


class FinnhubNewsProvider:
    """Fetches company news from Finnhub with keyword-based sentiment scoring.

    No daily rate limit — 60 req/min is very generous for our use case.
    Cache TTL prevents redundant calls within the same window.
    """

    def __init__(
        self,
        api_key: str,
        max_articles: int = 5,
        cache_ttl: float = 300.0,  # 5-min cache
        lookback_days: int = 2,  # fetch last 2 days of news
        min_delay: float = 1.0,  # min seconds between API calls (60 req/min safe)
    ) -> None:
        """
        Args:
            api_key:       Finnhub API key from finnhub.io/register.
            max_articles:  Max headlines to return per symbol.
            cache_ttl:     Seconds to cache results.
            lookback_days: How many days back to fetch news.
            min_delay:     Minimum seconds between requests (rate limit guard).
        """
        if not api_key or not api_key.strip():
            raise ValueError("Finnhub api_key must not be empty.")
        self._api_key = api_key.strip()
        self._max_articles = max_articles
        self._cache_ttl = cache_ttl
        self._lookback_days = lookback_days
        self._min_delay = min_delay
        self._last_request_at: float = 0.0
        self._cache: dict[str, tuple[list[dict], float]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_sentiment(self, symbol: str) -> list[dict]:
        """Fetch recent news with sentiment for a symbol.

        Returns:
            List of dicts with: title, sentiment_label, sentiment_score, source, time_published.
            Empty list on any error.
        """
        sym = symbol.strip().upper()

        cached = self._cache.get(sym)
        if cached is not None:
            articles, fetched_at = cached
            if time.monotonic() - fetched_at < self._cache_ttl:
                return articles

        try:
            articles = self._fetch_from_finnhub(sym)
            self._cache[sym] = (articles, time.monotonic())
            return articles
        except Exception as exc:
            _log.warning("Finnhub news failed for %s: %s", sym, exc)
            if cached:
                return cached[0]
            return []

    def format_for_prompt(self, symbol: str) -> str:
        """Return compact news summary for LLM prompt."""
        headlines = self.fetch_sentiment(symbol)
        if not headlines:
            return ""

        lines = [f"Recent news for {symbol} ({len(headlines)} articles, Finnhub):"]
        for h in headlines[: self._max_articles]:
            label = h.get("sentiment_label", "Neutral")
            score = h.get("sentiment_score", 0.0)
            title = h.get("title", "")[:80]
            lines.append(f"  [{label} {score:+.2f}] {title}")

        scores = [h.get("sentiment_score", 0.0) for h in headlines]
        avg = sum(scores) / len(scores) if scores else 0.0
        overall = "Bullish" if avg > 0.1 else "Bearish" if avg < -0.1 else "Neutral"
        lines.append(f"  Overall: {overall} (avg: {avg:+.3f})")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_from_finnhub(self, symbol: str) -> list[dict]:
        """Hit Finnhub company-news endpoint."""
        # Rate limit guard
        elapsed = time.monotonic() - self._last_request_at
        if self._last_request_at > 0 and elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)

        now = datetime.now(timezone.utc)
        date_to = now.strftime("%Y-%m-%d")
        date_from = (now - timedelta(days=self._lookback_days)).strftime("%Y-%m-%d")

        params = {
            "symbol": symbol,
            "from": date_from,
            "to": date_to,
            "token": self._api_key,
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
            if exc.code == 429:
                raise RuntimeError("Finnhub rate limit (429)") from exc
            raise RuntimeError(f"Finnhub HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"Finnhub network error: {exc}") from exc

        if not isinstance(data, list):
            return []

        articles = []
        for item in data[: self._max_articles]:
            headline = item.get("headline", "")
            score, label = _score_headline(headline)
            articles.append(
                {
                    "title": headline,
                    "source": item.get("source", ""),
                    "time_published": str(item.get("datetime", "")),
                    "sentiment_label": label,
                    "sentiment_score": score,
                }
            )

        _log.info("Finnhub news: %d articles for %s", len(articles), symbol)
        return articles
