"""
execution.models.order
========================

Order — immutable approved order request.

An Order is created by the RiskEngine after approving a DecisionEvent.
It represents a single trade instruction ready for paper (or live) execution.

Python Version: 3.11+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar, Literal
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Order:
    """Immutable approved trade order.

    Attributes:
        order_id:    Unique order identifier.
        symbol:      Canonical ticker symbol.
        action:      BUY or SELL.
        quantity:    Number of units. Must be > 0.
        order_type:  MARKET or LIMIT.
        limit_price: Required when order_type is LIMIT, else None.
        strategy_id: Originating strategy identifier.
        timestamp:   UTC creation time.
    """

    symbol: str
    action: Literal["BUY", "SELL"]
    quantity: float
    order_type: Literal["MARKET", "LIMIT"]
    strategy_id: str
    order_id: str = field(default_factory=lambda: str(uuid4()))
    limit_price: float | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    _VALID_ACTIONS: ClassVar[frozenset[str]] = frozenset({"BUY", "SELL"})
    _VALID_ORDER_TYPES: ClassVar[frozenset[str]] = frozenset({"MARKET", "LIMIT"})
    _MIN_QUANTITY: ClassVar[float] = 0.01

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must not be empty.")
        if self.action not in self._VALID_ACTIONS:
            raise ValueError(f"action must be BUY or SELL, got: {self.action!r}.")
        if self.quantity < self._MIN_QUANTITY:
            raise ValueError(f"quantity must be >= {self._MIN_QUANTITY}.")
        if self.order_type not in self._VALID_ORDER_TYPES:
            raise ValueError("order_type must be MARKET or LIMIT.")
        if self.order_type == "LIMIT" and (
            self.limit_price is None or self.limit_price <= 0
        ):
            raise ValueError("limit_price must be > 0 for LIMIT orders.")
        if not self.strategy_id or not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty.")

    def to_dict(self) -> dict[str, object]:
        ts = self.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "action": self.action,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "limit_price": self.limit_price,
            "strategy_id": self.strategy_id,
            "timestamp": ts.isoformat(),
        }

    def __str__(self) -> str:
        return (
            f"Order(id='{self.order_id}', symbol='{self.symbol}', "
            f"action='{self.action}', qty={self.quantity}, "
            f"type='{self.order_type}')"
        )
