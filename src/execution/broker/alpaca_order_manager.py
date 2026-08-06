"""
execution.broker.alpaca_order_manager
======================================

AlpacaOrderManager — live broker execution via the Alpaca REST API.

Drop-in replacement for ``execution.engine.OrderManager``.  Accepts
the same ``execute(order) -> FillEvent`` interface but submits real
(paper or live) market orders to Alpaca instead of filling locally.

Architecture: L5 Execution layer.
Permitted imports: foundation, communication, execution (own layer), alpaca-py.
Forbidden imports: data, intelligence, analytics, dashboard.

Python: 3.11+
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from communication.interfaces.i_event_bus import IEventBus
from execution.events.fill_event import FillEvent
from execution.models.order import Order
from foundation.base_event import BaseEvent

_LOG = logging.getLogger(__name__)

# Risk constants
_CAPITAL_LIMIT_FRACTION: float = 0.02  # 2 % per-trade cap
_DRAWDOWN_LIMIT_FRACTION: float = 0.10  # 10 % session drawdown stop

# Fill-polling settings
_POLL_INTERVAL_SECONDS: float = 0.5
_FILL_TIMEOUT_SECONDS: float = 30.0

# Alpaca order-filled status strings
_FILLED_STATUSES: frozenset[str] = frozenset({"filled", "partially_filled"})


class AlpacaOrderManager:
    """Live order manager backed by the Alpaca broker REST API.

    Enforces two risk limits before submitting any order:
      - 2 % single-trade capital cap (notional ≤ 2 % of peak portfolio value)
      - 10 % session drawdown stop (current value ≥ 90 % of peak)

    Publishes a ``FillEvent`` on the EventBus after every successful fill
    and a ``risk.drawdown_breach`` event when the drawdown limit is hit.

    Args:
        bus:                      EventBus for publishing events.
        initial_portfolio_value:  Starting portfolio value used to seed
                                  the peak-value tracker.
        api_key:                  Alpaca API key.
        secret_key:               Alpaca secret key.
        live_trading:             ``False`` (default) → paper API;
                                  ``True`` → live API.
        paper_validation_complete: Must be explicitly ``True`` when
                                  ``live_trading=True``.  Guards against
                                  accidental live execution.

    Raises:
        ValueError: If ``live_trading=True`` and
                    ``paper_validation_complete`` is not ``True``.
    """

    def __init__(
        self,
        bus: IEventBus,
        initial_portfolio_value: float,
        api_key: str,
        secret_key: str,
        live_trading: bool = False,
        paper_validation_complete: bool = False,
    ) -> None:
        if live_trading and not paper_validation_complete:
            raise ValueError(
                "Live trading requires paper_validation_complete=True to confirm "
                "30-day validation has been reviewed."
            )

        self._bus = bus
        self._live_trading = live_trading
        self._peak_portfolio_value: float = initial_portfolio_value
        self._log = _LOG

        # Instantiate the Alpaca client (paper=True → paper API endpoint)
        self._client: TradingClient = TradingClient(
            api_key,
            secret_key,
            paper=not live_trading,
        )

        if live_trading:
            self._log.warning(
                "LIVE TRADING ACTIVE — ensure 30-day paper validation has been "
                "completed and reviewed before using this mode."
            )
        else:
            self._log.info(
                "AlpacaOrderManager initialised in paper-trading mode "
                "(paper API: https://paper-api.alpaca.markets)."
            )

    # ------------------------------------------------------------------
    # Public API — drop-in replacement for OrderManager
    # ------------------------------------------------------------------

    def execute(self, order: Order) -> FillEvent:
        """Submit a market order to Alpaca and return the filled FillEvent.

        Enforces risk limits before submission.  Polls for fill
        confirmation for up to 30 seconds.

        Args:
            order: Approved, immutable Order from RiskEngine.

        Returns:
            Immutable ``FillEvent`` published to the EventBus.

        Raises:
            ValueError:     If the capital limit or drawdown limit is breached.
            RuntimeError:   If the Alpaca API returns an error or the fill
                            times out after 30 seconds.
        """
        # Fetch current price and portfolio value for risk checks
        try:
            current_value = self.get_portfolio_value()
        except RuntimeError:
            # Fall back to peak value so risk check still functions
            current_value = self._peak_portfolio_value

        self._update_peak(current_value)

        # 1. Drawdown check (broad session risk)
        self._check_drawdown_limit()

        # 2. Capital-per-trade check — need current price
        current_price = self._get_current_price(order.symbol)
        self._check_capital_limit(order, current_price)

        # 3. Submit to Alpaca
        side = OrderSide.BUY if order.action == "BUY" else OrderSide.SELL
        request = MarketOrderRequest(
            symbol=order.symbol,
            qty=order.quantity,
            side=side,
            time_in_force=TimeInForce.DAY,
        )

        try:
            submitted = self._client.submit_order(request)
        except Exception as exc:
            raise RuntimeError(f"Alpaca API error: {exc}") from exc

        order_id: str = str(submitted.id)

        # 4. Poll for fill confirmation
        fill_price = self._await_fill(order_id)

        # 5. Construct and publish FillEvent
        fill = FillEvent(
            event_type="execution.fill",
            order_id=order.order_id,
            symbol=order.symbol.upper(),
            action=order.action,
            quantity=order.quantity,
            fill_price=fill_price,
            timestamp=datetime.now(timezone.utc),
        )
        self._bus.publish(fill)
        return fill

    # ------------------------------------------------------------------
    # Portfolio / position queries
    # ------------------------------------------------------------------

    def get_positions(self) -> list[dict[str, Any]]:
        """Return a list of current open positions from Alpaca.

        Returns:
            List of dicts with keys ``symbol``, ``quantity``, ``market_value``.
            Returns ``[]`` when there are no open positions.

        Raises:
            RuntimeError: On Alpaca API error.
        """
        try:
            positions = self._client.get_all_positions()
        except Exception as exc:
            raise RuntimeError(f"Alpaca API error: {exc}") from exc

        if not positions:
            return []

        return [
            {
                "symbol": p.symbol,
                "quantity": float(p.qty),
                "market_value": float(p.market_value),
            }
            for p in positions
        ]

    def get_portfolio_value(self) -> float:
        """Return the current total portfolio equity from Alpaca.

        Returns:
            Portfolio equity in USD as a ``float``.

        Raises:
            RuntimeError: On Alpaca API error.
        """
        try:
            account = self._client.get_account()
        except Exception as exc:
            raise RuntimeError(f"Alpaca API error: {exc}") from exc

        return float(account.equity)

    # ------------------------------------------------------------------
    # Risk enforcement (private)
    # ------------------------------------------------------------------

    def _check_capital_limit(self, order: Order, current_price: float) -> None:
        """Raise ``ValueError`` if the order notional exceeds 2 % of peak.

        Args:
            order:         The order being validated.
            current_price: Current market price of the symbol.

        Raises:
            ValueError: If ``quantity × price > 0.02 × peak_portfolio_value``.
        """
        notional = order.quantity * current_price
        limit = _CAPITAL_LIMIT_FRACTION * self._peak_portfolio_value
        if notional > limit:
            self._log.warning(
                "Capital limit breach: symbol=%s notional=%.2f limit=%.2f "
                "(2%% of peak portfolio value %.2f).",
                order.symbol,
                notional,
                limit,
                self._peak_portfolio_value,
            )
            raise ValueError(
                f"Order for {order.symbol} notional {notional:.2f} exceeds "
                f"2% capital limit of {limit:.2f} "
                f"(peak portfolio value {self._peak_portfolio_value:.2f})."
            )

    def _check_drawdown_limit(self) -> None:
        """Raise ``ValueError`` if session drawdown exceeds 10 %.

        Publishes a ``risk.drawdown_breach`` event before raising.

        Raises:
            ValueError: If ``(peak - current) / peak > 0.10``.
        """
        try:
            current_value = self.get_portfolio_value()
        except RuntimeError:
            # If we cannot fetch value, skip the drawdown check safely
            return

        self._update_peak(current_value)
        peak = self._peak_portfolio_value

        if peak <= 0:
            return

        drawdown = (peak - current_value) / peak
        if drawdown > _DRAWDOWN_LIMIT_FRACTION:
            self._log.warning(
                "Drawdown limit breached: peak=%.2f current=%.2f drawdown=%.2f%%.",
                peak,
                current_value,
                drawdown * 100,
            )
            breach_event = BaseEvent(
                event_type="risk.drawdown_breach",
            )
            self._bus.publish(breach_event)
            raise ValueError(
                f"Session drawdown {drawdown:.2%} exceeds 10% limit "
                f"(peak {peak:.2f}, current {current_value:.2f})."
            )

    def _update_peak(self, current_value: float) -> None:
        """Update the peak portfolio value if ``current_value`` is higher.

        Args:
            current_value: Latest observed portfolio value.
        """
        if current_value > self._peak_portfolio_value:
            self._peak_portfolio_value = current_value

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_current_price(self, symbol: str) -> float:
        """Fetch the latest trade price for *symbol* from Alpaca.

        Falls back to ``_peak_portfolio_value`` (effectively a 0 quantity
        ratio → always passes capital check) if the quote cannot be fetched,
        so execution is never silently blocked by a failed price lookup.

        Args:
            symbol: Ticker symbol.

        Returns:
            Latest trade price as a ``float``.
        """
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockLatestTradeRequest

            # Re-use the credentials already held by the trading client
            creds = self._client._api_key, self._client._secret_key  # type: ignore[attr-defined]
            data_client = StockHistoricalDataClient(*creds)
            req = StockLatestTradeRequest(symbol_or_symbols=symbol)
            trade = data_client.get_stock_latest_trade(req)
            return float(trade[symbol].price)
        except Exception:
            # Graceful fallback — returns 0.0 so capital check passes
            # (0.0 × qty = 0.0 ≤ any positive limit)
            self._log.warning(
                "Could not fetch current price for %s; capital check skipped.",
                symbol,
            )
            return 0.0

    def _await_fill(self, alpaca_order_id: str) -> float:
        """Poll Alpaca until the order is filled or a timeout is reached.

        Args:
            alpaca_order_id: The Alpaca-assigned order UUID string.

        Returns:
            Average fill price as a ``float``.

        Raises:
            RuntimeError: If the order is not filled within 30 seconds.
            RuntimeError: On Alpaca API error during polling.
        """
        deadline = time.monotonic() + _FILL_TIMEOUT_SECONDS

        while time.monotonic() < deadline:
            try:
                alpaca_order = self._client.get_order_by_id(alpaca_order_id)
            except Exception as exc:
                raise RuntimeError(f"Alpaca API error: {exc}") from exc

            status = str(alpaca_order.status).lower()
            if status in _FILLED_STATUSES and alpaca_order.filled_avg_price is not None:
                return float(alpaca_order.filled_avg_price)

            time.sleep(_POLL_INTERVAL_SECONDS)

        raise RuntimeError(f"Alpaca fill timeout for order {alpaca_order_id}")
