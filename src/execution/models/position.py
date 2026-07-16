"""
execution.models.position
===========================

Position — immutable snapshot of a single holding.

Python Version: 3.11+
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class Position:
    """Immutable snapshot of a position in a symbol.

    Attributes:
        symbol:          Canonical ticker symbol.
        quantity:        Net quantity held (positive = long).
        avg_entry_price: Volume-weighted average entry price.
        current_price:   Latest mark-to-market price.
    """

    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float

    _MAX_SYMBOL_LENGTH: ClassVar[int] = 32

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must not be empty.")
        if self.avg_entry_price < 0:
            raise ValueError("avg_entry_price must not be negative.")
        if self.current_price < 0:
            raise ValueError("current_price must not be negative.")

    @property
    def market_value(self) -> float:
        """Current mark-to-market value of this position."""
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized P&L at current price."""
        return self.quantity * (self.current_price - self.avg_entry_price)

    @property
    def is_flat(self) -> bool:
        """Return True if position is effectively zero."""
        return abs(self.quantity) < 1e-9

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "avg_entry_price": self.avg_entry_price,
            "current_price": self.current_price,
            "market_value": self.market_value,
            "unrealized_pnl": self.unrealized_pnl,
        }
