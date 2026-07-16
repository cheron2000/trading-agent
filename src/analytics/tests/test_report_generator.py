"""
Unit tests for analytics.reports.report_generator.ReportGenerator.

All assertions use == (not is) except for None checks.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from analytics.journal.trade_journal import TradeJournal
from analytics.metrics.metrics_engine import MetricsEngine
from analytics.reports.report_generator import ReportGenerator
from execution.events.fill_event import FillEvent
from intelligence.events.decision_event import DecisionEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_fill(symbol: str = "AAPL", price: float = 150.0, qty: float = 10.0) -> FillEvent:
    return FillEvent(
        event_type="execution.fill",
        order_id="order-001",
        symbol=symbol,
        action="SELL",
        quantity=qty,
        fill_price=price,
        timestamp=datetime.now(timezone.utc),
    )


def _make_decision() -> DecisionEvent:
    return DecisionEvent(
        event_type="intelligence.decision",
        symbol="AAPL",
        action="BUY",
        confidence=0.8,
        rationale="test rationale",
        strategy_id="test-strategy",
    )


def _make_report(n_entries: int = 0, label: str = "") -> dict:
    engine = MetricsEngine(initial_capital=100_000.0)
    journal = TradeJournal()
    fill = _make_fill()
    decision = _make_decision()
    for _ in range(n_entries):
        engine.record_fill(fill, entry_price=140.0)
        journal.record(fill, decision)
    gen = ReportGenerator(engine, journal)
    return gen.generate(label=label)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestReportGenerator:

    def test_generate_returns_all_required_keys(self) -> None:
        report = _make_report()
        for key in ("label", "generated_at", "journal_integrity",
                    "total_journal_entries", "metrics", "recent_trades"):
            assert key in report

    def test_label_passed_through(self) -> None:
        report = _make_report(label="2024-01-15")
        assert report["label"] == "2024-01-15"

    def test_generated_at_is_iso8601_utc(self) -> None:
        report = _make_report()
        ts = report["generated_at"]
        assert isinstance(ts, str)
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None

    def test_journal_integrity_true_on_fresh_journal(self) -> None:
        report = _make_report(n_entries=3)
        assert report["journal_integrity"] == True

    def test_total_journal_entries_matches_count(self) -> None:
        report = _make_report(n_entries=5)
        assert report["total_journal_entries"] == 5

    def test_recent_trades_capped_at_10(self) -> None:
        report = _make_report(n_entries=12)
        assert len(report["recent_trades"]) == 10

    def test_metrics_dict_has_all_keys(self) -> None:
        report = _make_report(n_entries=2)
        metrics = report["metrics"]
        for key in ("total_trades", "total_pnl", "total_return",
                    "sharpe_ratio", "max_drawdown", "win_rate"):
            assert key in metrics

    def test_empty_journal_gives_empty_recent_trades(self) -> None:
        report = _make_report(n_entries=0)
        assert report["recent_trades"] == []
        assert report["total_journal_entries"] == 0
