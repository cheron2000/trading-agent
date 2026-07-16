"""
execution.engine.portfolio_tracker
=====================================

PortfolioTracker — applies FillEvents to a Portfolio and exposes positions.

Python Version: 3.11+
"""

from __future__ import annotations

from execution.events.fill_event import FillEvent
from execution.models.portfolio import Portfolio
from execution.models.position import Position


class PortfolioTracker:
    """Applies fills to a Portfolio and provides position queries.

    Wraps a ``Portfolio`` instance and provides a clean interface
    for the Analytics and Dashboard layers to query position state.
    """

    def __init__(self, portfolio: Portfolio) -> None:
        """
        Args:
            portfolio: Mutable Portfolio to track.
        """
        self._portfolio = portfolio

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply_fill(self, fill: FillEvent) -> None:
        """Apply a fill to the portfolio.

        Args:
            fill: Immutable FillEvent from the OrderManager.

        Raises:
            ValueError: If fill is None, or if the portfolio rejects it
                        (e.g. insufficient cash or position).
        """
        if fill is None:
            raise ValueError("fill must not be None.")

        if fill.action == "BUY":
            self._portfolio.apply_buy(
                symbol=fill.symbol,
                quantity=fill.quantity,
                price=fill.fill_price,
            )
        else:
            self._portfolio.apply_sell(
                symbol=fill.symbol,
                quantity=fill.quantity,
                price=fill.fill_price,
            )

    def get_position(
        self, symbol: str, current_price: float
    ) -> Position | None:
        """Return a Position snapshot for a symbol, or None if flat.

        Args:
            symbol:        Ticker symbol.
            current_price: Latest mark-to-market price.

        Returns:
            Immutable ``Position`` or ``None`` if not held.
        """
        raw = self._portfolio.get_position(symbol)
        if raw is None:
            return None
        qty, avg_entry = raw
        if abs(qty) < 1e-9:
            return None
        return Position(
            symbol=symbol,
            quantity=qty,
            avg_entry_price=avg_entry,
            current_price=current_price,
        )

    def portfolio_value(self, price_feed: dict[str, float]) -> float:
        """Return total portfolio value at current prices.

        Args:
            price_feed: Symbol → current price mapping.

        Returns:
            Cash + sum of mark-to-market position values.
        """
        return self._portfolio.portfolio_value(price_feed)

    @property
    def cash(self) -> float:
        """Return current cash balance."""
        return self._portfolio.cash
