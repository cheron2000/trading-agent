"""
Tests for YFinanceProvider.warm_cache's time-budget and interruptibility.

Covers the fix for: total network failure across all symbols could
previously consume far more wall-clock time than a caller's configured
run duration before returning, and wasn't responsive to a stop signal.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from data.providers.yfinance_provider import YFinanceProvider


@pytest.fixture
def provider() -> YFinanceProvider:
    return YFinanceProvider(symbols=["AAPL", "MSFT", "GOOGL"])


class TestWarmCacheTimeoutBudget:
    def test_no_budget_is_backward_compatible(self, provider: YFinanceProvider) -> None:
        """timeout_seconds=None (default) preserves old unbounded behavior."""
        with patch.object(provider._yf, "download", return_value=None):
            provider.warm_cache()  # should return promptly on empty data, not raise

    def test_rate_limited_failure_respects_timeout_budget(
        self, provider: YFinanceProvider
    ) -> None:
        with patch.object(
            provider._yf, "download", side_effect=Exception("429 Too Many Requests")
        ):
            start = time.monotonic()
            provider.warm_cache(timeout_seconds=1.5)
            elapsed = time.monotonic() - start

        # Old behavior (3 retries with 2s/4s backoff) would take ~6s+;
        # budgeted behavior should stop close to the requested budget.
        assert elapsed < 3.0

    def test_should_stop_interrupts_before_budget_expires(
        self, provider: YFinanceProvider
    ) -> None:
        stop_at = time.monotonic() + 0.5
        with patch.object(
            provider._yf, "download", side_effect=Exception("429 Too Many Requests")
        ):
            start = time.monotonic()
            provider.warm_cache(
                timeout_seconds=10.0,  # generous budget
                should_stop=lambda: time.monotonic() > stop_at,
            )
            elapsed = time.monotonic() - start

        assert elapsed < 2.0  # stopped well before the 10s budget

    def test_no_timeout_and_no_should_stop_still_returns_on_non_rate_limit_error(
        self, provider: YFinanceProvider
    ) -> None:
        """Non-rate-limit exceptions already fail fast without retry."""
        with patch.object(provider._yf, "download", side_effect=ValueError("boom")):
            start = time.monotonic()
            provider.warm_cache()
            elapsed = time.monotonic() - start
        assert elapsed < 1.0


class TestFetchTimeoutBudget:
    def test_fetch_respects_timeout_budget_on_persistent_failure(
        self, provider: YFinanceProvider
    ) -> None:
        with patch.object(
            provider._yf, "download", side_effect=Exception("429 Too Many Requests")
        ):
            start = time.monotonic()
            with pytest.raises(ValueError, match="No data available"):
                provider.fetch("AAPL", timeout_seconds=1.0)
            elapsed = time.monotonic() - start
        assert elapsed < 2.5

    def test_fetch_recent_respects_timeout_budget_on_persistent_failure(
        self, provider: YFinanceProvider
    ) -> None:
        with patch.object(
            provider._yf, "download", side_effect=Exception("429 Too Many Requests")
        ):
            start = time.monotonic()
            with pytest.raises(ValueError, match="No data available"):
                provider.fetch_recent("AAPL", n=5, timeout_seconds=1.0)
            elapsed = time.monotonic() - start
        assert elapsed < 2.5


class TestShouldAbortHelper:
    def test_should_abort_true_when_deadline_passed(self) -> None:
        past_deadline = time.monotonic() - 1
        assert YFinanceProvider._should_abort(past_deadline, None) is True

    def test_should_abort_false_when_deadline_in_future(self) -> None:
        future_deadline = time.monotonic() + 60
        assert YFinanceProvider._should_abort(future_deadline, None) is False

    def test_should_abort_true_when_should_stop_true(self) -> None:
        assert YFinanceProvider._should_abort(None, lambda: True) is True

    def test_should_abort_false_when_both_none(self) -> None:
        assert YFinanceProvider._should_abort(None, None) is False


class TestInterruptibleSleep:
    def test_sleeps_full_duration_when_uninterrupted(self) -> None:
        start = time.monotonic()
        YFinanceProvider._interruptible_sleep(0.6, None, None)
        assert time.monotonic() - start >= 0.55

    def test_stops_early_when_should_stop_becomes_true(self) -> None:
        stop_at = time.monotonic() + 0.3
        start = time.monotonic()
        YFinanceProvider._interruptible_sleep(
            5.0, None, lambda: time.monotonic() > stop_at
        )
        elapsed = time.monotonic() - start
        assert elapsed < 1.0
