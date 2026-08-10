"""
analytics.metrics.metrics_engine
==================================

MetricsEngine — computes trading performance metrics from fill history.

Metrics: total_return, sharpe_ratio, max_drawdown, win_rate, total_trades.
All computations are deterministic and reference-dataset-testable.

Python Version: 3.11+
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import ClassVar

from execution.events.fill_event import FillEvent


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    """Immutable snapshot of computed performance metrics.

    Attributes:
        total_trades:   Number of fills processed.
        total_pnl:      Sum of realized P&L across all fills.
        total_return:   Return as a fraction of initial capital.
        sharpe_ratio:   Annualised Sharpe ratio (0.0 if < 2 trades).
        max_drawdown:   Maximum peak-to-trough drawdown fraction.
        win_rate:       Fraction of profitable trades (0.0 if no trades).
    """

    total_trades: int
    total_pnl: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float

    def to_dict(self) -> dict[str, object]:
        return {
            "total_trades": self.total_trades,
            "total_pnl": round(self.total_pnl, 6),
            "total_return": round(self.total_return, 6),
            "sharpe_ratio": round(self.sharpe_ratio, 6),
            "max_drawdown": round(self.max_drawdown, 6),
            "win_rate": round(self.win_rate, 6),
        }


class MetricsEngine:
    """Computes performance metrics from a sequence of FillEvents.

    Usage::

        engine = MetricsEngine(initial_capital=100_000.0)
        engine.record_fill(fill, entry_price=150.0)
        metrics = engine.compute()
    """

    ANNUALISATION_FACTOR: ClassVar[float] = math.sqrt(252)

    def __init__(self, initial_capital: float = 100_000.0) -> None:
        """
        Args:
            initial_capital: Starting portfolio value for return calculation.

        Raises:
            ValueError: If initial_capital <= 0.
        """
        if initial_capital <= 0:
            raise ValueError("initial_capital must be > 0.")
        self._initial_capital = initial_capital
        # List of per-trade P&L values
        self._trade_pnls: list[float] = []
        # Running equity curve for drawdown
        self._equity_curve: list[float] = [initial_capital]

    # ------------------------------------------------------------------
    # Data ingestion
    # ------------------------------------------------------------------

    def record_fill(self, fill: FillEvent, entry_price: float) -> None:
        """Record a fill and its entry price for P&L computation.

        For BUY fills, entry_price is the cost basis.
        For SELL fills, entry_price is the price at which the position was entered.

        P&L = (fill_price - entry_price) * quantity  for BUY→SELL round trips.
        We compute it simply as:
            SELL → pnl = (fill_price - entry_price) * quantity
            BUY  → pnl = 0  (entry recorded, realized on exit)

        Args:
            fill:        The FillEvent to record.
            entry_price: The average entry price for this position.

        Raises:
            ValueError: If fill is None or entry_price <= 0.
        """
        if fill is None:
            raise ValueError("fill must not be None.")
        if entry_price <= 0:
            raise ValueError("entry_price must be > 0.")

        if fill.action == "SELL":
            pnl = (fill.fill_price - entry_price) * fill.quantity
            self._trade_pnls.append(pnl)
            last_equity = self._equity_curve[-1]
            self._equity_curve.append(last_equity + pnl)

    # ------------------------------------------------------------------
    # Metrics computation
    # ------------------------------------------------------------------

    def compute(self) -> PerformanceMetrics:
        """Compute and return a PerformanceMetrics snapshot.

        Returns:
            Immutable ``PerformanceMetrics`` from all recorded fills.
        """
        total_trades = len(self._trade_pnls)
        total_pnl = sum(self._trade_pnls)
        total_return = total_pnl / self._initial_capital

        sharpe = self._compute_sharpe()
        max_dd = self._compute_max_drawdown()
        win_rate = (
            sum(1 for p in self._trade_pnls if p > 0) / total_trades
            if total_trades > 0
            else 0.0
        )

        return PerformanceMetrics(
            total_trades=total_trades,
            total_pnl=total_pnl,
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
        )

    def _compute_sharpe(self) -> float:
        """Annualised Sharpe ratio. Returns 0.0 if fewer than 2 trades."""
        if len(self._trade_pnls) < 2:
            return 0.0
        mean = statistics.mean(self._trade_pnls)
        std = statistics.pstdev(self._trade_pnls)
        if std == 0:
            return 0.0
        return (mean / std) * self.ANNUALISATION_FACTOR

    def _compute_max_drawdown(self) -> float:
        """Maximum peak-to-trough drawdown as a fraction."""
        if len(self._equity_curve) < 2:
            return 0.0
        peak = self._equity_curve[0]
        max_dd = 0.0
        for value in self._equity_curve:
            peak = max(peak, value)
            dd = (peak - value) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return max_dd
