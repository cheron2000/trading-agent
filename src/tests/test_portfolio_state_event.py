"""
src/tests/test_portfolio_state_event.py
========================================

Unit tests for PortfolioStateEvent model immutability, construction, and serialization.
"""
import pytest
from communication.events.portfolio_state_event import PortfolioStateEvent


def test_portfolio_state_event_construction():
    pos = ({"symbol": "AAPL", "quantity": 10.0, "entry_price": 150.0},)
    evt = PortfolioStateEvent(
        portfolio_value=10550.0,
        cash=9050.0,
        realized_pnl=550.0,
        total_return_pct=5.5,
        positions=pos,
    )

    assert evt.event_type == "portfolio.state"
    assert evt.portfolio_value == 10550.0
    assert evt.cash == 9050.0
    assert evt.realized_pnl == 550.0
    assert evt.total_return_pct == 5.5
    assert len(evt.positions) == 1
    assert evt.positions[0]["symbol"] == "AAPL"


def test_portfolio_state_event_immutability():
    evt = PortfolioStateEvent(portfolio_value=10000.0)
    with pytest.raises(AttributeError):
        evt.portfolio_value = 20000.0  # dataclass frozen


def test_portfolio_state_event_to_dict():
    pos = ({"symbol": "BTC-USD", "quantity": 0.5, "entry_price": 60000.0},)
    evt = PortfolioStateEvent(
        portfolio_value=40000.0,
        cash=10000.0,
        realized_pnl=200.0,
        total_return_pct=2.0,
        positions=pos,
    )

    d = evt.to_dict()
    assert d["event_type"] == "portfolio.state"
    assert d["portfolio_value"] == 40000.0
    assert d["cash"] == 10000.0
    assert d["realized_pnl"] == 200.0
    assert d["total_return_pct"] == 2.0
    assert isinstance(d["positions"], list)
    assert d["positions"][0]["symbol"] == "BTC-USD"
