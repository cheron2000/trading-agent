"""
communication.events.portfolio_state_event
===========================================

PortfolioStateEvent — published each trading cycle by run_hour.py.

Lives in the Communication Layer (L2) so it is importable by both
L5 Execution (publisher) and L7 Dashboard/Telegram (subscriber)
without creating a cross-layer import violation.

Python: 3.13+
"""

from __future__ import annotations

from dataclasses import dataclass, field

from foundation.base_event import BaseEvent


@dataclass(frozen=True, slots=True)
class PortfolioStateEvent(BaseEvent):
    """Snapshot of portfolio state for a single trading cycle.

    Published by run_hour.py at the end of each symbol-processing
    loop. Consumed by TelegramNotifier to populate /status, /positions,
    and /pnl command replies.

    All fields carry only primitives (no L5 objects) so this event
    can cross layer boundaries safely.

    Attributes:
        portfolio_value:  Total portfolio value (cash + positions) in USD.
        cash:             Uninvested cash balance in USD.
        realized_pnl:     Cumulative realized profit/loss for the session.
        total_return_pct: Return percentage relative to starting capital.
        positions:        Immutable tuple of open position dicts.
                          Each dict: {"symbol": str, "quantity": float,
                                      "entry_price": float}.
    """

    event_type: str = "portfolio.state"
    portfolio_value: float = 0.0
    cash: float = 0.0
    realized_pnl: float = 0.0
    total_return_pct: float = 0.0
    positions: tuple[dict, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        """Serialize the event including portfolio fields.

        Returns:
            Dictionary representation of the event.
        """
        base = super().to_dict()
        base.update(
            {
                "portfolio_value": self.portfolio_value,
                "cash": self.cash,
                "realized_pnl": self.realized_pnl,
                "total_return_pct": self.total_return_pct,
                "positions": list(self.positions),
            }
        )
        return base
