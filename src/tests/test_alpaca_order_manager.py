"""
src/tests/test_alpaca_order_manager.py
=======================================

Unit tests for AlpacaOrderManager risk gates and paper trading instantiation.
"""

import pytest
from unittest.mock import MagicMock
from execution.broker.alpaca_order_manager import AlpacaOrderManager


def test_alpaca_order_manager_live_gate():
    mock_bus = MagicMock()
    # Attempting live trading without paper_validation_complete MUST raise ValueError
    with pytest.raises(
        ValueError, match="Live trading requires paper_validation_complete=True"
    ):
        AlpacaOrderManager(
            bus=mock_bus,
            initial_portfolio_value=10000.0,
            api_key="PKTEST123456",
            secret_key="secret123456",
            live_trading=True,
            paper_validation_complete=False,
        )


def test_alpaca_order_manager_paper_init(monkeypatch):
    mock_bus = MagicMock()
    mock_trading_client = MagicMock()

    # Patch TradingClient to avoid real API calls during init
    monkeypatch.setattr(
        "execution.broker.alpaca_order_manager.TradingClient",
        lambda key, secret, paper: mock_trading_client,
    )

    mgr = AlpacaOrderManager(
        bus=mock_bus,
        initial_portfolio_value=10000.0,
        api_key="PKTEST123456",
        secret_key="secret123456",
        live_trading=False,
    )

    assert mgr._live_trading is False
    assert mgr._peak_portfolio_value == 10000.0
