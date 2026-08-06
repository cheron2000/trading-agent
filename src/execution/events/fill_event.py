"""execution.events.fill_event — Published after a paper execution fill."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from foundation.base_event import BaseEvent


@dataclass(frozen=True, slots=True)
class FillEvent(BaseEvent):
    """Event carrying fill details after paper execution.

    Attributes:
        order_id:   The order that was filled.
        symbol:     Ticker symbol.
        action:     BUY or SELL.
        quantity:   Units filled.
        fill_price: Execution price.
        timestamp:  UTC fill time.
    """

    order_id: str = ""
    symbol: str = ""
    action: Literal["BUY", "SELL"] = "BUY"
    quantity: float = 0.0
    fill_price: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.order_id or not self.order_id.strip():
            raise ValueError("order_id must not be empty.")
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must not be empty.")
        if self.action not in ("BUY", "SELL"):
            raise ValueError("action must be BUY or SELL.")
        if self.quantity <= 0:
            raise ValueError("quantity must be > 0.")
        if self.fill_price <= 0:
            raise ValueError("fill_price must be > 0.")

    def to_dict(self) -> dict[str, object]:
        base = BaseEvent.to_dict(self)
        ts = self.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        base.update(
            {
                "order_id": self.order_id,
                "symbol": self.symbol,
                "action": self.action,
                "quantity": self.quantity,
                "fill_price": self.fill_price,
                "fill_timestamp": ts.isoformat(),
            }
        )
        return base
