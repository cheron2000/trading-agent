"""
data.providers.yf_news_provider
=================================

YFNewsProvider — Yahoo Finance news headlines via yfinance.

No API key required. No rate limits. Uses the same yfinance library
already installed. Zero extra dependencies.

Headlines are scored with simple keyword-based sentiment — not as
accurate as Finnhub or AV but completely free and always available.

Python Version: 3.11+
"""

from __future__ import annotations

import logging
import time

_log = logging.getLogger(__name__)

# Sentiment keyword sets (same as Finnhub provider)
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
    "high",
    "rises",
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
    "low",
    "sinks",
    "slumps",
}


def _score_headline(headline: str) -> tuple[float, str]:
    words = set(headline.lower().split())
    bull = len(words & _BULLISH_WORDS)
    bear = len(words & _BEARISH_WORDS)

    if bull == 0 and bear == 0:
        return 0.0, "Neutral"
    total = bull + bear
    score = round((bull - bear) / total, 3)

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
    return score, label


class YFNewsProvider:
    """Yahoo Finance news via yfinance. No API key, no rate limits.

    Used as the always-available fallback when Finnhub and AV are unavailable.
    Cache TTL prevents hammering the same ticker repeatedly.
    """

    def __init__(
        self,
        max_articles: int = 5,
        cache_ttl: float = 300.0,  # 5-min cache
        min_delay: float = 2.0,  # courtesy delay between requests
    ) -> None:
        self._max_articles = max_articles
        self._cache_ttl = cache_ttl
        self._min_delay = min_delay
        self._last_request_at: float = 0.0
        self._cache: dict[str, tuple[list[dict], float]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_sentiment(self, symbol: str) -> list[dict]:
        """Fetch Yahoo Finance news headlines for a symbol.

        Returns:
            List of article dicts. Empty list on error.
        """
        sym = symbol.strip().upper()

        cached = self._cache.get(sym)
        if cached is not None:
            articles, fetched_at = cached
            if time.monotonic() - fetched_at < self._cache_ttl:
                return articles

        try:
            articles = self._fetch_from_yf(sym)
            self._cache[sym] = (articles, time.monotonic())
            return articles
        except Exception as exc:
            _log.warning("YF news failed for %s: %s", sym, exc)
            if cached:
                return cached[0]
            return []

    def format_for_prompt(self, symbol: str) -> str:
        """Return compact news summary for LLM prompt."""
        headlines = self.fetch_sentiment(symbol)
        if not headlines:
            return ""

        lines = [
            f"Recent news for {symbol} ({len(headlines)} articles, Yahoo Finance):"
        ]
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

    def _fetch_from_yf(self, symbol: str) -> list[dict]:
        """Fetch headlines via yfinance Ticker.news."""
        # Courtesy delay
        elapsed = time.monotonic() - self._last_request_at
        if self._last_request_at > 0 and elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)

        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("yfinance not installed") from exc

        ticker = yf.Ticker(symbol)
        self._last_request_at = time.monotonic()

        raw_news = getattr(ticker, "news", None)
        if not raw_news:
            # Try calling as method if it's callable
            try:
                raw_news = ticker.get_news()
            except Exception:
                raw_news = []

        if not raw_news:
            return []

        articles = []
        for item in raw_news[: self._max_articles]:
            # yfinance news item structure varies by version
            title = (
                item.get("title", "") or item.get("content", {}).get("title", "")
                if isinstance(item.get("content"), dict)
                else ""
            )
            if not title:
                continue

            pub_time = item.get("providerPublishTime", item.get("pubDate", ""))
            source = item.get("publisher", item.get("source", "Yahoo Finance"))

            score, label = _score_headline(title)
            articles.append(
                {
                    "title": title,
                    "source": source,
                    "time_published": str(pub_time),
                    "sentiment_label": label,
                    "sentiment_score": score,
                }
            )

        _log.info("YF news: %d articles for %s", len(articles), symbol)
        return articles
