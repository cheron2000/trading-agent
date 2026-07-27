"""
analytics.reports.report_generator
=====================================

ReportGenerator — produces end-of-day summary reports.

Combines MetricsEngine output and TradeJournal entries into a
structured, serializable report dict. No file I/O here — callers
decide how to persist or display the report.

Python Version: 3.11+
"""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.journal.trade_journal import TradeJournal
from analytics.metrics.metrics_engine import MetricsEngine


class ReportGenerator:
    """Generates end-of-day performance reports.

    Usage::

        report = ReportGenerator(engine, journal)
        data = report.generate(label="2024-01-15")
    """

    def __init__(
        self,
        metrics_engine: MetricsEngine,
        journal: TradeJournal,
    ) -> None:
        self._metrics_engine = metrics_engine
        self._journal = journal

    def generate(self, label: str = "") -> dict[str, object]:
        """Generate a report snapshot.

        Args:
            label: Optional human-readable label (e.g. date string).

        Returns:
            Dictionary containing metrics, journal summary, and metadata.
        """
        metrics = self._metrics_engine.compute()
        entries = self._journal.entries()
        integrity_ok = self._journal.verify_integrity()

        return {
            "label": label,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "journal_integrity": integrity_ok,
            "total_journal_entries": len(entries),
            "metrics": metrics.to_dict(),
            "recent_trades": [e.to_dict() for e in entries[-10:]],
        }
