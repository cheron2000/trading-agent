"""
Property-based tests for AlpacaOrderManager.

Feature: telegram-alpaca-integration

Tests covered:
  - Property 9:  execute() produces a correctly populated FillEvent
  - Property 10: Orders exceeding 2% of portfolio value are rejected
  - Property 11: All orders rejected when drawdown > 10%; peak tracked correctly
  - Property 12: get_positions() maps Alpaca API response to standard dict structure
"""

from __future__ import annotations

import math
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from execution.broker.alpaca_order_manager import AlpacaOrderManager
from execution.models.order import Order

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_bus() -> MagicMock:
    """Return a mock EventBus."""
    bus = MagicMock()
    bus.publish = MagicMock()
    return bus


def _make_manager(
    bus: MagicMock,
    portfolio_value: float = 100_000.0,
    live_trading: bool = False,
) -> AlpacaOrderManager:
    """Construct an AlpacaOrderManager with a mocked TradingClient."""
    with patch("execution.broker.alpaca_order_manager.TradingClient"):
        mgr = AlpacaOrderManager(
            bus=bus,
            initial_portfolio_value=portfolio_value,
            api_key="TEST_KEY",
            secret_key="TEST_SECRET",
            live_trading=live_trading,
            paper_validation_complete=live_trading,  # satisfy gate when live
        )
    return mgr


def _make_order(
    symbol: str = "AAPL",
    action: str = "BUY",
    quantity: float = 1.0,
) -> Order:
    return Order(
        symbol=symbol,
        action=action,  # type: ignore[arg-type]
        quantity=quantity,
        order_type="MARKET",
        strategy_id="test-strategy",
    )


# Hypothesis strategies for valid Order fields
_symbols = st.text(
    alphabet=st.characters(whitelist_categories=("Lu",)), min_size=1, max_size=5
).filter(lambda s: s.strip() != "")
_actions = st.sampled_from(["BUY", "SELL"])
_quantities = st.floats(
    min_value=0.01, max_value=1_000.0, allow_nan=False, allow_infinity=False
)
_prices = st.floats(
    min_value=0.01, max_value=100_000.0, allow_nan=False, allow_infinity=False
)
_portfolio_values = st.floats(
    min_value=100.0, max_value=10_000_000.0, allow_nan=False, allow_infinity=False
)


# ---------------------------------------------------------------------------
# Property 9 — execute() produces a correctly populated FillEvent
# Feature: telegram-alpaca-integration, Property 9: AlpacaOrderManager
# execute() produces a correctly populated FillEvent from API response
# Validates: Requirements 6.2, 6.3
# ---------------------------------------------------------------------------


@given(
    symbol=_symbols,
    action=_actions,
    quantity=_quantities,
    avg_fill_price=_prices,
)
@settings(max_examples=100)
def test_property_9_execute_fill_event_correctness(
    symbol: str,
    action: str,
    quantity: float,
    avg_fill_price: float,
) -> None:
    """Property 9: execute() produces a correctly populated FillEvent.

    Validates: Requirements 6.2, 6.3
    """
    bus = _make_bus()
    portfolio_value = 100_000.0
    # Make notional safe: ensure quantity * price <= 2% * portfolio_value
    # (1% to give headroom for floating point rounding)
    max_notional = 0.01 * portfolio_value  # stay within capital limit
    safe_qty = min(quantity, max_notional / avg_fill_price)
    assume(safe_qty >= 0.01)

    order = _make_order(symbol=symbol, action=action, quantity=safe_qty)

    mock_client = MagicMock()

    # Mock submitted order
    mock_submitted = MagicMock()
    mock_submitted.id = "alpaca-order-uuid-001"
    mock_client.submit_order.return_value = mock_submitted

    # Mock polled order (filled)
    mock_filled = MagicMock()
    mock_filled.status = "filled"
    mock_filled.filled_avg_price = str(avg_fill_price)
    mock_client.get_order_by_id.return_value = mock_filled

    # Mock account (no drawdown)
    mock_account = MagicMock()
    mock_account.equity = str(portfolio_value)
    mock_client.get_account.return_value = mock_account

    # Mock get_all_positions (no positions)
    mock_client.get_all_positions.return_value = []

    with patch(
        "execution.broker.alpaca_order_manager.TradingClient", return_value=mock_client
    ):
        mgr = AlpacaOrderManager(
            bus=bus,
            initial_portfolio_value=portfolio_value,
            api_key="KEY",
            secret_key="SECRET",
        )

    # Patch price fetch to return safe price
    with patch.object(mgr, "_get_current_price", return_value=avg_fill_price):
        fill = mgr.execute(order)

    # Assertions
    assert fill.event_type == "execution.fill"
    assert fill.symbol == order.symbol.upper()
    assert fill.action == order.action
    assert math.isclose(fill.quantity, order.quantity, rel_tol=1e-9)
    assert math.isclose(fill.fill_price, avg_fill_price, rel_tol=1e-9)

    # Published exactly once
    bus.publish.assert_called_once_with(fill)


# ---------------------------------------------------------------------------
# Property 10 — Orders exceeding 2% of portfolio value are rejected
# Feature: telegram-alpaca-integration, Property 10: Orders exceeding 2%
# Validates: Requirements 9.1
# ---------------------------------------------------------------------------


@given(
    quantity=_quantities,
    price=_prices,
    portfolio_value=_portfolio_values,
)
@settings(max_examples=100)
def test_property_10_capital_limit_enforcement(
    quantity: float,
    price: float,
    portfolio_value: float,
) -> None:
    """Property 10: Orders exceeding 2% of portfolio value are rejected.

    Validates: Requirements 9.1
    """
    bus = _make_bus()
    notional = quantity * price
    limit = 0.02 * portfolio_value

    with patch("execution.broker.alpaca_order_manager.TradingClient"):
        mgr = AlpacaOrderManager(
            bus=bus,
            initial_portfolio_value=portfolio_value,
            api_key="KEY",
            secret_key="SECRET",
        )

    order = Order(
        symbol="TSLA",
        action="BUY",
        quantity=quantity,
        order_type="MARKET",
        strategy_id="test",
    )

    if notional > limit:
        with pytest.raises(ValueError):
            mgr._check_capital_limit(order, price)
        # Alpaca submit_order must NOT have been called
        mgr._client.submit_order.assert_not_called()  # type: ignore[attr-defined]
    else:
        # Should not raise
        try:
            mgr._check_capital_limit(order, price)
        except ValueError:
            pytest.fail(
                f"Capital check raised unexpectedly: notional={notional:.4f}, "
                f"limit={limit:.4f}"
            )


# ---------------------------------------------------------------------------
# Property 11 — Drawdown rejection + peak tracking
# Feature: telegram-alpaca-integration, Property 11: All orders rejected when
# session drawdown exceeds 10%, and drawdown breach event is published
# Validates: Requirements 9.2, 9.5
# ---------------------------------------------------------------------------


@given(
    portfolio_values=st.lists(
        st.floats(
            min_value=1.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False
        ),
        min_size=2,
        max_size=20,
    )
)
@settings(max_examples=100)
def test_property_11_drawdown_rejection_and_peak_tracking(
    portfolio_values: list[float],
) -> None:
    """Property 11: Drawdown rejection + correct peak tracking.

    Validates: Requirements 9.2, 9.5
    """
    bus = _make_bus()
    initial_value = portfolio_values[0]

    with patch("execution.broker.alpaca_order_manager.TradingClient"):
        mgr = AlpacaOrderManager(
            bus=bus,
            initial_portfolio_value=initial_value,
            api_key="KEY",
            secret_key="SECRET",
        )

    expected_peak = initial_value

    for value in portfolio_values:
        # Feed the value to _update_peak
        mgr._update_peak(value)
        expected_peak = max(expected_peak, value)

        # Peak must always equal the running maximum
        assert math.isclose(mgr._peak_portfolio_value, expected_peak, rel_tol=1e-9), (
            f"Peak mismatch: got {mgr._peak_portfolio_value}, "
            f"expected {expected_peak}"
        )

        # Check drawdown condition
        drawdown = (expected_peak - value) / expected_peak if expected_peak > 0 else 0.0

        if drawdown > 0.10:
            # Drawdown check should raise and publish breach event
            with patch.object(mgr, "get_portfolio_value", return_value=value):
                # Reset peak to expected_peak (may have been modified by _check_drawdown_limit)
                mgr._peak_portfolio_value = expected_peak
                bus.publish.reset_mock()
                with pytest.raises(ValueError):
                    mgr._check_drawdown_limit()

            # Verify breach event was published
            published_events = [call.args[0] for call in bus.publish.call_args_list]
            breach_events = [
                e for e in published_events if e.event_type == "risk.drawdown_breach"
            ]
            assert len(breach_events) >= 1, (
                f"Expected risk.drawdown_breach event, got: "
                f"{[e.event_type for e in published_events]}"
            )
        else:
            # Should not raise for drawdown within limits
            with patch.object(mgr, "get_portfolio_value", return_value=value):
                mgr._peak_portfolio_value = expected_peak
                try:
                    mgr._check_drawdown_limit()
                except ValueError:
                    pytest.fail(
                        f"Drawdown check raised unexpectedly: "
                        f"peak={expected_peak:.2f}, current={value:.2f}, "
                        f"drawdown={drawdown:.4f}"
                    )


# ---------------------------------------------------------------------------
# Property 12 — get_positions() maps Alpaca API response to standard dict
# Feature: telegram-alpaca-integration, Property 12: get_positions() maps
# Alpaca API response to standard dict structure
# Validates: Requirements 10.1, 10.3
# ---------------------------------------------------------------------------


def _make_mock_position(symbol: str, qty: float, market_value: float) -> MagicMock:
    pos = MagicMock()
    pos.symbol = symbol
    pos.qty = str(qty)
    pos.market_value = str(market_value)
    return pos


@given(
    positions=st.lists(
        st.fixed_dictionaries(
            {
                "symbol": st.text(
                    alphabet=st.characters(whitelist_categories=("Lu",)),
                    min_size=1,
                    max_size=5,
                ).filter(lambda s: s.strip() != ""),
                "qty": st.floats(
                    min_value=0.01,
                    max_value=10_000.0,
                    allow_nan=False,
                    allow_infinity=False,
                ),
                "market_value": st.floats(
                    min_value=0.01,
                    max_value=10_000_000.0,
                    allow_nan=False,
                    allow_infinity=False,
                ),
            }
        ),
        min_size=0,
        max_size=20,
    )
)
@settings(max_examples=100)
def test_property_12_get_positions_mapping(
    positions: list[dict[str, Any]],
) -> None:
    """Property 12: get_positions() maps Alpaca response to standard dict.

    Validates: Requirements 10.1, 10.3
    """
    bus = _make_bus()
    mock_client = MagicMock()

    mock_positions = [
        _make_mock_position(p["symbol"], p["qty"], p["market_value"]) for p in positions
    ]
    mock_client.get_all_positions.return_value = mock_positions

    with patch(
        "execution.broker.alpaca_order_manager.TradingClient", return_value=mock_client
    ):
        mgr = AlpacaOrderManager(
            bus=bus,
            initial_portfolio_value=100_000.0,
            api_key="KEY",
            secret_key="SECRET",
        )

    result = mgr.get_positions()

    # Empty positions returns empty list
    if not positions:
        assert result == []
        return

    assert len(result) == len(positions)

    for item in result:
        # Every dict must have exactly the three required keys
        assert set(item.keys()) == {
            "symbol",
            "quantity",
            "market_value",
        }, f"Unexpected keys in position dict: {set(item.keys())}"
        # All values must be present
        assert isinstance(item["symbol"], str)
        assert isinstance(item["quantity"], float)
        assert isinstance(item["market_value"], float)
