"""
Unit tests for execution.events.order_event.OrderEvent.

All assertions use == (not is) except for None checks.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from execution.events.order_event import OrderEvent
from execution.models.order import Order


def _make_order() -> Order:
    return Order(
        symbol="AAPL",
        action="BUY",
        quantity=10.0,
        order_type="MARKET",
        strategy_id="test-strategy",
    )


class TestOrderEvent:

    def test_valid_construction(self) -> None:
        order = _make_order()
        event = OrderEvent(event_type="execution.order", order=order)
        assert event.order == order

    def test_none_order_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="order must not be None"):
            OrderEvent(event_type="execution.order", order=None)

    def test_to_dict_contains_order_key(self) -> None:
        order = _make_order()
        event = OrderEvent(event_type="execution.order", order=order)
        d = event.to_dict()
        assert "order" in d
        assert d["order"]["symbol"] == "AAPL"

    def test_event_type_set_correctly(self) -> None:
        order = _make_order()
        event = OrderEvent(event_type="execution.order", order=order)
        assert event.event_type == "execution.order"

    def test_immutability(self) -> None:
        order = _make_order()
        event = OrderEvent(event_type="execution.order", order=order)
        with pytest.raises((FrozenInstanceError, AttributeError)):
            event.order = _make_order()  # type: ignore[misc]
