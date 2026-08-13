"""
data.providers.news_aggregator
================================

NewsAggregator — unified news layer with automatic fallback chain.

Priority order:
  1. Finnhub     — best quality, 60 req/min free, real-time
  2. AV News     — good quality, 25 req/day/key, 15-min delay
  3. Yahoo RSS   — keyword sentiment only, unlimited, always available

The aggregator tries Finnhub first. If unavailable (no key or error),
falls back to AV. If AV is rate-limited, falls back to Yahoo Finance.
Each source has its own cache so no redundant calls are made.

Rate limit protection:
  - Each provider enforces its own minimum delay between requests
  - Per-source TTL cache (5 min default) prevents burst calls
  - Aggregator tracks which sources are healthy vs degraded

Python Version: 3.11+
"""

from __future__ import annotations

import logging
from typing import Literal

_log = logging.getLogger(__name__)

SourceName = Literal["finnhub", "alphavantage", "yahoo", "none"]


class NewsAggregator:
    """Unified news layer — tries Finnhub → AV → Yahoo in order.

    Usage::

        agg = NewsAggregator(
            finnhub_key="your_key",    # optional
            av_keys=["KEY1","KEY2"],   # optional
        )
        # In trading loop:
        agg.advance_av_key()           # rotate AV key each cycle
        context = agg.format_for_prompt("AAPL")  # inject into LLM prompt
    """

    def __init__(
        self,
        finnhub_key: str | None = None,
        av_keys: list[str] | None = None,
        max_articles: int = 5,
        cache_ttl: float = 300.0,
    ) -> None:
        """
        Args:
            finnhub_key:   Finnhub API key. If None, Finnhub is skipped.
            av_keys:       Alpha Vantage API keys. If None, AV is skipped.
            max_articles:  Max headlines per symbol.
            cache_ttl:     Cache TTL in seconds (shared setting).
        """
        self._finnhub = None
        self._av = None
        self._yf = None

        # Init Finnhub
        if finnhub_key and finnhub_key.strip():
            try:
                from data.providers.finnhub_news_provider import FinnhubNewsProvider

                self._finnhub = FinnhubNewsProvider(
                    api_key=finnhub_key,
                    max_articles=max_articles,
                    cache_ttl=cache_ttl,
                )
                _log.info("NewsAggregator: Finnhub provider ready.")
            except Exception as exc:
                _log.warning("NewsAggregator: Finnhub init failed: %s", exc)

        # Init Alpha Vantage
        if av_keys and any(av_keys):
            try:
                from data.providers.av_news_provider import AVNewsProvider

                self._av = AVNewsProvider(
                    api_keys=av_keys,
                    max_articles=max_articles,
                    cache_ttl=cache_ttl,
                )
                _log.info(
                    "NewsAggregator: AV News provider ready (%d keys).", len(av_keys)
                )
            except Exception as exc:
                _log.warning("NewsAggregator: AV init failed: %s", exc)

        # Always init Yahoo Finance (no key needed)
        try:
            from data.providers.yf_news_provider import YFNewsProvider

            self._yf = YFNewsProvider(
                max_articles=max_articles,
                cache_ttl=cache_ttl,
            )
            _log.info("NewsAggregator: Yahoo Finance provider ready.")
        except Exception as exc:
            _log.warning("NewsAggregator: YF init failed: %s", exc)

        # Track which providers are currently healthy
        self._degraded: set[str] = set()

    # ------------------------------------------------------------------
    # Key rotation (call once per trading cycle)
    # ------------------------------------------------------------------

    def advance_av_key(self) -> None:
        """Rotate AV key. Call once per cycle."""
        if self._av is not None:
            self._av.advance_key()

    # ------------------------------------------------------------------
    # Main interface
    # ------------------------------------------------------------------

    def format_for_prompt(self, symbol: str) -> str:
        """Return news context string for LLM prompt.

        Tries Finnhub → AV → Yahoo in order.
        Returns empty string if all sources fail.

        Args:
            symbol: Ticker symbol (e.g. "AAPL").
        """
        sym = symbol.strip().upper()

        # 1. Try Finnhub
        if self._finnhub is not None and "finnhub" not in self._degraded:
            try:
                result = self._finnhub.format_for_prompt(sym)
                if result:
                    self._degraded.discard("finnhub")  # recover if was degraded
                    return result
            except Exception as exc:
                _log.warning("Finnhub degraded for %s: %s — trying AV", sym, exc)
                self._degraded.add("finnhub")

        # 2. Try Alpha Vantage
        if self._av is not None and "av" not in self._degraded:
            try:
                result = self._av.format_for_prompt(sym)
                if result:
                    self._degraded.discard("av")
                    return result
            except Exception as exc:
                _log.warning("AV news degraded for %s: %s — trying Yahoo", sym, exc)
                self._degraded.add("av")

        # 3. Yahoo Finance fallback (always try, even if degraded before)
        if self._yf is not None:
            try:
                result = self._yf.format_for_prompt(sym)
                if result:
                    return result
            except Exception as exc:
                _log.warning("YF news failed for %s: %s", sym, exc)

        return ""  # all sources failed — LLM uses price features only

    def get_sentiment_score(self, symbol: str) -> float:
        """Calculate aggregate numeric sentiment score (-1.0 to +1.0) for symbol.

        Args:
            symbol: Ticker symbol (e.g. "AAPL").

        Returns:
            Float sentiment score between -1.0 and +1.0 (0.0 if no news or neutral).
        """
        sym = symbol.strip().upper()
        headlines = []

        if self._finnhub is not None and "finnhub" not in self._degraded:
            try:
                headlines = self._finnhub.get_headlines(sym)
            except Exception:
                pass

        if not headlines and self._av is not None and "av" not in self._degraded:
            try:
                headlines = self._av.get_headlines(sym)
            except Exception:
                pass

        if not headlines and self._yf is not None:
            try:
                headlines = self._yf.get_headlines(sym)
            except Exception:
                pass

        if not headlines:
            return 0.0

        scores = [h.get("sentiment_score", 0.0) for h in headlines if "sentiment_score" in h]
        if not scores:
            return 0.0

        avg_score = sum(scores) / len(scores)
        return max(-1.0, min(1.0, float(avg_score)))

    def status(self) -> dict:
        """Return health status of all news sources."""
        return {
            "finnhub": (
                "ready"
                if self._finnhub and "finnhub" not in self._degraded
                else ("degraded" if self._finnhub else "not_configured")
            ),
            "alphavantage": (
                "ready"
                if self._av and "av" not in self._degraded
                else ("degraded" if self._av else "not_configured")
            ),
            "yahoo": "ready" if self._yf else "not_configured",
        }
