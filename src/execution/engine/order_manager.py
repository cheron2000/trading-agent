"""
execution.engine.order_manager
================================

OrderManager — paper trading execution engine.

Fills orders immediately at the current price_feed price.
No slippage model in this phase (Phase 2 addition).
Live broker path raises NotImplementedError by design.

Python Version: 3.11+
"""

from __future__ import annotations

from datetime import datetime, timezone

from communication.interfaces.i_event_bus import IEventBus
from execution.events.fill_event import FillEvent
from execution.models.order import Order


class OrderManager:
    """Paper trading order executor.

    Fills orders at the current price from an injected price_feed
    and publishes a FillEvent on the EventBus.

    Live trading is explicitly not supported — raises NotImplementedError
    to prevent accidental real-money execution.
    """

    def __init__(
        self,
        price_feed: dict[str, float],
        bus: IEventBus,
        live_mode: bool = False,
    ) -> None:
        """
        Args:
            price_feed: Symbol → current price mapping.
            bus:        EventBus to publish FillEvents on.
            live_mode:  Must remain False — live trading not implemented.

        Raises:
            NotImplementedError: If live_mode is True.
        """
        if live_mode:
            raise NotImplementedError(
                "Live trading is not permitted until paper trading "
                "validation completes. See build report Section 5."
            )
        self._price_feed = price_feed
        self._bus = bus

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, order: Order) -> FillEvent:
        """Paper-fill an order at the current price_feed price.

        Args:
            order: Approved, immutable Order from RiskEngine.

        Returns:
            Immutable ``FillEvent`` published to the EventBus.

        Raises:
            ValueError: If the symbol is not in price_feed.
        """
        symbol = order.symbol.upper()
        if symbol not in self._price_feed:
            raise ValueError(f"Symbol '{symbol}' not in price feed — cannot fill.")

        fill_price = self._price_feed[symbol]
        now = datetime.now(timezone.utc)

        fill = FillEvent(
            event_type="execution.fill",
            order_id=order.order_id,
            symbol=symbol,
            action=order.action,
            quantity=order.quantity,
            fill_price=fill_price,
            timestamp=now,
        )

        self._bus.publish(fill)
        return fill
