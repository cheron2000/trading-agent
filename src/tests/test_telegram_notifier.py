"""
src/tests/test_telegram_notifier.py
===================================

Unit tests for TelegramNotifier constructor validation, message formatting, and portfolio cache updates.
"""

from types import SimpleNamespace
import pytest
from unittest.mock import MagicMock
from dashboard.telegram.telegram_notifier import TelegramNotifier
from foundation.base_event import BaseEvent


def test_telegram_notifier_init_validation():
    mock_bus = MagicMock()
    with pytest.raises(ValueError, match="bot_token must not be empty"):
        TelegramNotifier(bus=mock_bus, bot_token="", chat_id="123456")

    with pytest.raises(ValueError, match="chat_id must not be empty"):
        TelegramNotifier(bus=mock_bus, bot_token="token_123", chat_id="   ")


def test_telegram_notifier_format_decision_message():
    mock_bus = MagicMock()
    notifier = TelegramNotifier(bus=mock_bus, bot_token="test_token", chat_id="123456")

    event = SimpleNamespace(
        event_type="intelligence.decision",
        symbol="AAPL",
        action="BUY",
        confidence=0.85,
        rationale="A" * 300,
    )

    msg = notifier._format_decision_message(event)
    assert "🤖 Decision Digest" in msg
    assert "Symbol:     AAPL" in msg
    assert "Action:     BUY" in msg
    assert "Confidence: 0.85" in msg
    assert len(msg.split("Rationale:  ")[1]) == 200


def test_telegram_notifier_format_fill_message():
    mock_bus = MagicMock()
    notifier = TelegramNotifier(bus=mock_bus, bot_token="test_token", chat_id="123456")

    event = SimpleNamespace(
        event_type="execution.fill",
        symbol="BTC-USD",
        action="SELL",
        quantity=0.5,
        fill_price=65000.0,
        timestamp=None,
    )

    msg = notifier._format_fill_message(event, realized_pnl=2500.0)
    assert "✅ Trade Fill — SELL" in msg
    assert "Symbol:    BTC-USD" in msg
    assert "Qty:       0.5000" in msg
    assert "Price:     65000.00" in msg
    assert "P&L:       +2500.00" in msg


def test_telegram_notifier_portfolio_event_cache():
    mock_bus = MagicMock()
    notifier = TelegramNotifier(bus=mock_bus, bot_token="test_token", chat_id="123456")

    event = SimpleNamespace(
        event_type="portfolio.state",
        portfolio_value=12500.0,
        cash=10000.0,
        realized_pnl=500.0,
        total_return_pct=5.0,
        positions=({"symbol": "TSLA", "quantity": 10, "entry_price": 250.0},),
    )

    notifier._on_portfolio(event)
    assert notifier._portfolio_value == 12500.0
    assert notifier._cash == 10000.0
    assert notifier._realized_pnl == 500.0
    assert len(notifier._positions) == 1
