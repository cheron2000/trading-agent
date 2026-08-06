"""
Unit tests for AlpacaOrderManager.__init__ validation.

Feature: telegram-alpaca-integration, Task 2.3

Tests:
  - live_trading=True, paper_validation_complete=False → ValueError with exact message
  - live_trading=True, paper_validation_complete omitted → ValueError
  - Paper mode → TradingClient called with paper=True, INFO log
  - Live mode → TradingClient called with paper=False, WARNING log
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from execution.broker.alpaca_order_manager import AlpacaOrderManager


def _make_bus() -> MagicMock:
    """Return a mock EventBus."""
    bus = MagicMock()
    return bus


# ---------------------------------------------------------------------------
# Test: live_trading=True, paper_validation_complete=False → ValueError
# Requirement: 8.2
# ---------------------------------------------------------------------------


def test_init_live_trading_requires_paper_validation_complete_flag():
    """Test that live_trading=True without paper_validation_complete=True raises ValueError."""
    bus = _make_bus()

    with patch("execution.broker.alpaca_order_manager.TradingClient"):
        with pytest.raises(ValueError) as exc_info:
            AlpacaOrderManager(
                bus=bus,
                initial_portfolio_value=100_000.0,
                api_key="TEST_KEY",
                secret_key="TEST_SECRET",
                live_trading=True,
                paper_validation_complete=False,
            )

    assert str(exc_info.value) == (
        "Live trading requires paper_validation_complete=True to confirm "
        "30-day validation has been reviewed."
    )


# ---------------------------------------------------------------------------
# Test: live_trading=True, paper_validation_complete omitted → ValueError
# Requirement: 8.3
# ---------------------------------------------------------------------------


def test_init_live_trading_requires_paper_validation_complete_when_omitted():
    """Test that live_trading=True without paper_validation_complete parameter raises ValueError."""
    bus = _make_bus()

    with patch("execution.broker.alpaca_order_manager.TradingClient"):
        with pytest.raises(ValueError) as exc_info:
            AlpacaOrderManager(
                bus=bus,
                initial_portfolio_value=100_000.0,
                api_key="TEST_KEY",
                secret_key="TEST_SECRET",
                live_trading=True,
                # paper_validation_complete is omitted (defaults to False)
            )

    assert str(exc_info.value) == (
        "Live trading requires paper_validation_complete=True to confirm "
        "30-day validation has been reviewed."
    )


# ---------------------------------------------------------------------------
# Test: Paper mode → TradingClient called with paper=True, INFO log
# Requirement: 12.2, 8.1
# ---------------------------------------------------------------------------


def test_init_paper_mode_creates_client_with_paper_true():
    """Test that paper mode (default) instantiates TradingClient with paper=True."""
    bus = _make_bus()

    mock_client = MagicMock()
    with patch(
        "execution.broker.alpaca_order_manager.TradingClient", return_value=mock_client
    ) as mock_trading_client_class:
        mgr = AlpacaOrderManager(
            bus=bus,
            initial_portfolio_value=100_000.0,
            api_key="TEST_KEY",
            secret_key="TEST_SECRET",
            live_trading=False,  # Paper mode (default)
        )

    # Verify TradingClient was called with correct parameters
    mock_trading_client_class.assert_called_once_with(
        "TEST_KEY",
        "TEST_SECRET",
        paper=True,
    )
    assert mgr._client is mock_client


def test_init_paper_mode_logs_info_with_url():
    """Test that paper mode logs INFO message including paper API URL."""
    bus = _make_bus()

    with patch("execution.broker.alpaca_order_manager.TradingClient"):
        with patch("execution.broker.alpaca_order_manager._LOG") as mock_log:
            _ = AlpacaOrderManager(
                bus=bus,
                initial_portfolio_value=100_000.0,
                api_key="TEST_KEY",
                secret_key="TEST_SECRET",
                live_trading=False,  # Paper mode
            )

    # Verify INFO log was called
    mock_log.info.assert_called_once()
    call_args = mock_log.info.call_args[0][0]
    assert "paper-trading mode" in call_args.lower()
    assert "https://paper-api.alpaca.markets" in call_args


# ---------------------------------------------------------------------------
# Test: Live mode → TradingClient called with paper=False, WARNING log
# Requirement: 12.1, 12.4
# ---------------------------------------------------------------------------


def test_init_live_mode_creates_client_with_paper_false():
    """Test that live mode instantiates TradingClient with paper=False."""
    bus = _make_bus()

    mock_client = MagicMock()
    with patch(
        "execution.broker.alpaca_order_manager.TradingClient", return_value=mock_client
    ) as mock_trading_client_class:
        mgr = AlpacaOrderManager(
            bus=bus,
            initial_portfolio_value=100_000.0,
            api_key="TEST_KEY",
            secret_key="TEST_SECRET",
            live_trading=True,
            paper_validation_complete=True,
        )

    # Verify TradingClient was called with paper=False for live trading
    mock_trading_client_class.assert_called_once_with(
        "TEST_KEY",
        "TEST_SECRET",
        paper=False,
    )
    assert mgr._client is mock_client


def test_init_live_mode_logs_warning():
    """Test that live mode logs WARNING message about live trading activation."""
    bus = _make_bus()

    with patch("execution.broker.alpaca_order_manager.TradingClient"):
        with patch("execution.broker.alpaca_order_manager._LOG") as mock_log:
            _ = AlpacaOrderManager(
                bus=bus,
                initial_portfolio_value=100_000.0,
                api_key="TEST_KEY",
                secret_key="TEST_SECRET",
                live_trading=True,
                paper_validation_complete=True,
            )

    # Verify WARNING log was called
    mock_log.warning.assert_called_once()
    call_args = mock_log.warning.call_args[0][0]
    assert "LIVE TRADING ACTIVE" in call_args
    assert "30-day paper validation" in call_args


# ---------------------------------------------------------------------------
# Test: Peak portfolio value is initialized
# Requirement: 12.3
# ---------------------------------------------------------------------------


def test_init_sets_peak_portfolio_value():
    """Test that __init__ sets self._peak_portfolio_value to initial_portfolio_value."""
    bus = _make_bus()
    initial_value = 123_456.78

    with patch("execution.broker.alpaca_order_manager.TradingClient"):
        mgr = AlpacaOrderManager(
            bus=bus,
            initial_portfolio_value=initial_value,
            api_key="TEST_KEY",
            secret_key="TEST_SECRET",
        )

    assert mgr._peak_portfolio_value == initial_value


# ---------------------------------------------------------------------------
# Test: Parameters are correctly stored
# Requirement: 7.1
# ---------------------------------------------------------------------------


def test_init_stores_bus_and_live_trading_flag():
    """Test that __init__ stores the bus and live_trading flag correctly."""
    bus = _make_bus()

    with patch("execution.broker.alpaca_order_manager.TradingClient"):
        mgr = AlpacaOrderManager(
            bus=bus,
            initial_portfolio_value=100_000.0,
            api_key="TEST_KEY",
            secret_key="TEST_SECRET",
            live_trading=False,
        )

    assert mgr._bus is bus
    assert mgr._live_trading is False


def test_init_stores_live_trading_flag_when_true():
    """Test that __init__ correctly stores live_trading=True."""
    bus = _make_bus()

    with patch("execution.broker.alpaca_order_manager.TradingClient"):
        mgr = AlpacaOrderManager(
            bus=bus,
            initial_portfolio_value=100_000.0,
            api_key="TEST_KEY",
            secret_key="TEST_SECRET",
            live_trading=True,
            paper_validation_complete=True,
        )

    assert mgr._live_trading is True
