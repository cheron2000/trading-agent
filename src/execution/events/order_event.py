"""execution.events.order_event — Published after RiskEngine approves an order."""

from __future__ import annotations

from dataclasses import dataclass

from foundation.base_event import BaseEvent
from execution.models.order import Order


@dataclass(frozen=True, slots=True)
class OrderEvent(BaseEvent):
    """Event carrying an approved Order for paper/live execution.

    Attributes:
        order: The approved, immutable Order.
    """

    order: Order = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.order is None:
            raise ValueError("order must not be None.")

    def to_dict(self) -> dict[str, object]:
        base = super().to_dict()
        base["order"] = self.order.to_dict()
        return base
