"""
execution.risk.risk_engine
============================

RiskEngine — validates DecisionEvents and sizes orders.

Gates on confidence threshold, rejects HOLD, calculates quantity
from portfolio cash allocation, and enforces a minimum quantity floor.

Python Version: 3.11+
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar

from intelligence.events.decision_event import DecisionEvent
from execution.models.order import Order
from execution.models.portfolio import Portfolio


class RiskEngine:
    """Risk gate and position sizer for the Execution Layer.

    Converts approved DecisionEvents into sized Orders. Returns None
    for any decision that fails the risk gate.

    Rules (in order):
      1. HOLD → reject (return None)
      2. confidence < min_confidence → reject
      3. symbol not in price_feed → reject
      4. quantity = (cash * max_position_pct) / price
      5. quantity < MIN_QUANTITY → reject
      6. (positions_value + new order cost) / equity > max_total_exposure_pct
         → reject. Caps how much of total equity can be committed across
         *all* open positions combined, not just this one order — without
         this, several per-symbol-capped buys in the same cycle can still
         stack into an outsized total exposure.
      7. Return approved Order
    """

    MIN_QUANTITY: ClassVar[float] = 0.01

    def __init__(
        self,
        price_feed: dict[str, float],
        max_position_pct: float = 0.10,
        min_confidence: float = 0.60,
        max_total_exposure_pct: float = 0.60,
    ) -> None:
        """
        Args:
            price_feed:             Symbol → current price mapping.
            max_position_pct:       Max fraction of cash per position (0–1).
            min_confidence:         Minimum confidence to approve (0–1).
            max_total_exposure_pct: Max fraction of total equity
                                     (cash + all positions, marked to
                                     current price_feed) that may be
                                     committed across all open positions
                                     combined, including the new order.

        Raises:
            ValueError: On invalid parameter ranges.
        """
        if not (0.0 < max_position_pct <= 1.0):
            raise ValueError("max_position_pct must be in (0, 1].")
        if not (0.0 <= min_confidence <= 1.0):
            raise ValueError("min_confidence must be in [0, 1].")
        if not (0.0 < max_total_exposure_pct <= 1.0):
            raise ValueError("max_total_exposure_pct must be in (0, 1].")

        self._price_feed = price_feed
        self._max_position_pct = max_position_pct
        self._min_confidence = min_confidence
        self._max_total_exposure_pct = max_total_exposure_pct

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def approve(
        self,
        decision: DecisionEvent,
        portfolio: Portfolio,
    ) -> Order | None:
        """Evaluate a decision and return a sized Order or None.

        Args:
            decision:  The DecisionEvent from the Intelligence Layer.
            portfolio: Current portfolio state for cash calculation.

        Returns:
            Approved ``Order`` or ``None`` if rejected.
        """
        # Gate 1 — HOLD is never an order
        if decision.action == "HOLD":
            return None

        # Gate 2 — confidence threshold
        if decision.confidence < self._min_confidence:
            return None

        # Gate 3 — price must be known
        symbol = decision.symbol.upper()
        if symbol not in self._price_feed:
            return None

        price = self._price_feed[symbol]
        if price <= 0:
            return None

        # Gate 4 — size the position
        quantity = (portfolio.cash * self._max_position_pct) / price
        quantity = round(quantity, 6)

        # Gate 5 — quantity floor
        if quantity < self.MIN_QUANTITY:
            return None

        # Gate 6 — aggregate portfolio exposure cap
        cost = quantity * price
        positions_value = self._positions_value(portfolio)
        equity = portfolio.cash + positions_value
        if equity <= 0:
            return None
        projected_exposure = (positions_value + cost) / equity
        if projected_exposure > self._max_total_exposure_pct:
            return None

        return Order(
            symbol=symbol,
            action=decision.action,  # type: ignore[arg-type]
            quantity=quantity,
            order_type="MARKET",
            strategy_id=decision.strategy_id,
            timestamp=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _positions_value(self, portfolio: Portfolio) -> float:
        """Mark all open positions to current price_feed prices.

        Falls back to each position's average entry price if a symbol
        is not currently in price_feed, rather than dropping it from
        the exposure calculation.
        """
        total = 0.0
        for symbol, (qty, avg_price) in portfolio.all_positions().items():
            mark = self._price_feed.get(symbol, avg_price)
            total += qty * mark
        return total
