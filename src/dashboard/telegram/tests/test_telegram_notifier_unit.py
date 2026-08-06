"""
Unit tests for TelegramNotifier — task 4.16.

Tests cover:
  - Bot API failure on fill/decision/session → WARNING logged, no crash
  - /stop publishes shutdown event BEFORE sending reply (ordering assertion)
  - Unknown command → help text contains all four command names
  - Constructor validation (ValueError on empty bot_token / chat_id)
  - start() registers exactly four EventBus subscriptions
  - stop() unregisters all subscriptions

All tests mock python-telegram-bot Application and the EventBus to avoid
real network calls. The module under test is imported once at module level
so that patch() targets resolve correctly.
"""

from __future__ import annotations

import sys
import os
import unittest
from datetime import datetime, timezone
from typing import Callable
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Path bootstrap so tests can resolve src/ packages
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# ---------------------------------------------------------------------------
# Pre-import the module under test so patch() targets resolve correctly.
# We mock Application before the very first import so the module-level
# import of telegram.ext succeeds without a real bot token.
# ---------------------------------------------------------------------------
from foundation.base_event import BaseEvent  # noqa: E402
from communication.models.subscription import Subscription  # noqa: E402
import dashboard.telegram.telegram_notifier as _tn_module  # noqa: E402
from dashboard.telegram.telegram_notifier import TelegramNotifier  # noqa: E402


# ---------------------------------------------------------------------------
# Simple event stub — lets us attach arbitrary fields without inheriting
# from frozen BaseEvent dataclasses.
# ---------------------------------------------------------------------------


class _EventStub:
    """Lightweight stand-in for any event type used in tests.

    Stores all kwargs as attributes; also exposes event_id and event_type
    so it satisfies the informal BaseEvent interface that TelegramNotifier
    uses via getattr().
    """

    def __init__(self, event_type: str = "test.event", **fields):
        self.event_type = event_type
        self.event_id = "test-event-id"
        for k, v in fields.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# Helpers — lightweight fake EventBus
# ---------------------------------------------------------------------------


class _FakeBus:
    """Minimal in-memory EventBus for unit tests."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = {}
        self._subscriptions: list[Subscription] = []

    def subscribe(self, pattern: str, handler: Callable) -> Subscription:
        from uuid import uuid4

        sub = Subscription(subscriber_id=str(uuid4()), event_pattern=pattern)
        self._handlers.setdefault(pattern, []).append(handler)
        self._subscriptions.append(sub)
        return sub

    def unsubscribe(self, subscription: Subscription) -> None:
        self._subscriptions = [s for s in self._subscriptions if s != subscription]

    def publish(self, event: BaseEvent) -> None:
        handlers = self._handlers.get(event.event_type, [])
        for h in handlers:
            h(event)

    @property
    def subscription_count(self) -> int:
        return len(self._subscriptions)


def _build_notifier(bus=None, notify_hold: bool = False, **kwargs) -> TelegramNotifier:
    """Build a TelegramNotifier with Application mocked at module level."""
    if bus is None:
        bus = _FakeBus()
    with patch.object(_tn_module, "Application", MagicMock()):
        n = TelegramNotifier(
            bus=bus,
            bot_token="fake:TOKEN",
            chat_id="123456",
            notify_hold=notify_hold,
            **kwargs,
        )
    return n


# ---------------------------------------------------------------------------
# 1. Constructor validation
# ---------------------------------------------------------------------------


class TestConstructorValidation(unittest.TestCase):

    def test_empty_bot_token_raises(self):
        with patch.object(_tn_module, "Application", MagicMock()):
            with self.assertRaises(ValueError) as ctx:
                TelegramNotifier(bus=_FakeBus(), bot_token="", chat_id="123")
        self.assertIn("bot_token must not be empty", str(ctx.exception))

    def test_whitespace_bot_token_raises(self):
        with patch.object(_tn_module, "Application", MagicMock()):
            with self.assertRaises(ValueError) as ctx:
                TelegramNotifier(bus=_FakeBus(), bot_token="   ", chat_id="123")
        self.assertIn("bot_token must not be empty", str(ctx.exception))

    def test_empty_chat_id_raises(self):
        with patch.object(_tn_module, "Application", MagicMock()):
            with self.assertRaises(ValueError) as ctx:
                TelegramNotifier(bus=_FakeBus(), bot_token="tok", chat_id="")
        self.assertIn("chat_id must not be empty", str(ctx.exception))

    def test_whitespace_chat_id_raises(self):
        with patch.object(_tn_module, "Application", MagicMock()):
            with self.assertRaises(ValueError) as ctx:
                TelegramNotifier(bus=_FakeBus(), bot_token="tok", chat_id="  ")
        self.assertIn("chat_id must not be empty", str(ctx.exception))


# ---------------------------------------------------------------------------
# 2. start() / stop() subscription management
# ---------------------------------------------------------------------------


class TestSubscriptionManagement(unittest.TestCase):

    def _notifier_with_mock_thread(self):
        bus = _FakeBus()
        n = _build_notifier(bus=bus)
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = False
        with patch.object(_tn_module, "threading") as mock_threading:
            mock_threading.Thread.return_value = mock_thread
            # Build a mock Application that the start() code can call
            mock_app = MagicMock()
            n._app = None  # reset to allow start() to rebuild

            with patch.object(_tn_module, "Application") as MockApp:
                MockApp.builder.return_value.token.return_value.build.return_value = (
                    mock_app
                )
                n.start()
        return n, bus, mock_thread

    def test_start_registers_four_subscriptions(self):
        n, bus, _ = self._notifier_with_mock_thread()
        self.assertEqual(bus.subscription_count, 4)

    def test_stop_unregisters_all_subscriptions(self):
        n, bus, _ = self._notifier_with_mock_thread()
        n._loop = None  # prevents run_coroutine_threadsafe from being called
        n._thread = None
        n.stop()
        self.assertEqual(bus.subscription_count, 0)


# ---------------------------------------------------------------------------
# 3. Message formatters
# ---------------------------------------------------------------------------


class TestFormatFillMessage(unittest.TestCase):

    def setUp(self):
        self.n = _build_notifier()

    def _make_fill_event(self, action, symbol="AAPL", qty=1.5, price=150.0):
        return _EventStub(
            event_type="execution.fill",
            action=action,
            symbol=symbol,
            quantity=qty,
            fill_price=price,
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        )

    def test_buy_message_contains_symbol(self):
        ev = self._make_fill_event("BUY", symbol="TSLA")
        msg = self.n._format_fill_message(ev, None)
        self.assertIn("TSLA", msg)

    def test_buy_message_contains_quantity_4dp(self):
        ev = self._make_fill_event("BUY", qty=1.23456)
        msg = self.n._format_fill_message(ev, None)
        self.assertIn("1.2346", msg)

    def test_buy_message_contains_price_2dp(self):
        ev = self._make_fill_event("BUY", price=123.456)
        msg = self.n._format_fill_message(ev, None)
        self.assertIn("123.46", msg)

    def test_buy_message_contains_timestamp(self):
        ev = self._make_fill_event("BUY")
        msg = self.n._format_fill_message(ev, None)
        self.assertIn("2024-01-15", msg)

    def test_sell_message_contains_pnl_with_sign(self):
        ev = self._make_fill_event("SELL")
        msg = self.n._format_fill_message(ev, realized_pnl=42.50)
        self.assertIn("+42.50", msg)

    def test_sell_message_negative_pnl(self):
        ev = self._make_fill_event("SELL")
        msg = self.n._format_fill_message(ev, realized_pnl=-10.0)
        self.assertIn("-10.00", msg)

    def test_buy_message_no_pnl_field(self):
        ev = self._make_fill_event("BUY")
        msg = self.n._format_fill_message(ev, None)
        self.assertNotIn("P&L", msg)


class TestFormatDecisionMessage(unittest.TestCase):

    def setUp(self):
        self.n = _build_notifier()

    def _make_decision(self, action="BUY", rationale="test rationale"):
        return _EventStub(
            event_type="intelligence.decision",
            symbol="AAPL",
            action=action,
            confidence=0.85,
            rationale=rationale,
        )

    def test_contains_symbol(self):
        ev = self._make_decision()
        msg = self.n._format_decision_message(ev)
        self.assertIn("AAPL", msg)

    def test_contains_action(self):
        ev = self._make_decision(action="SELL")
        msg = self.n._format_decision_message(ev)
        self.assertIn("SELL", msg)

    def test_contains_confidence_2dp(self):
        ev = self._make_decision()
        msg = self.n._format_decision_message(ev)
        self.assertIn("0.85", msg)

    def test_rationale_truncated_to_200(self):
        long_rationale = "x" * 500
        ev = self._make_decision(rationale=long_rationale)
        msg = self.n._format_decision_message(ev)
        for line in msg.split("\n"):
            if "Rationale" in line:
                _, _, val = line.partition(":")
                self.assertLessEqual(len(val.strip()), 200)


class TestFormatSessionSummary(unittest.TestCase):

    def setUp(self):
        self.n = _build_notifier()

    def test_no_trades_message(self):
        payload = {
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "portfolio_value": 10000.00,
        }
        msg = self.n._format_session_summary(payload)
        self.assertIn("No trades", msg)
        self.assertIn("10000.00", msg)

    def test_trades_message_contains_all_metrics(self):
        payload = {
            "total_pnl": 150.75,
            "win_rate": 0.667,
            "total_trades": 12,
            "sharpe_ratio": 1.2345,
            "max_drawdown": 0.0532,
            "portfolio_value": 11000.00,
        }
        msg = self.n._format_session_summary(payload)
        self.assertIn("+150.75", msg)
        self.assertIn("66.7%", msg)
        self.assertIn("12", msg)
        self.assertIn("1.2345", msg)


class TestFormatStatusReply(unittest.TestCase):

    def setUp(self):
        self.n = _build_notifier()
        self.n._portfolio_value = 12345.67
        self.n._cash = 3456.78

    def test_contains_portfolio_value(self):
        msg = self.n._format_status_reply()
        self.assertIn("12345.67", msg)

    def test_contains_cash(self):
        msg = self.n._format_status_reply()
        self.assertIn("3456.78", msg)


class TestFormatPositionsReply(unittest.TestCase):

    def setUp(self):
        self.n = _build_notifier()

    def test_no_positions(self):
        self.n._positions = []
        msg = self.n._format_positions_reply()
        self.assertEqual(msg, "No open positions.")

    def test_one_position(self):
        self.n._positions = [
            {"symbol": "AAPL", "quantity": 10.5, "entry_price": 175.50}
        ]
        msg = self.n._format_positions_reply()
        self.assertIn("AAPL", msg)
        self.assertIn("10.5000", msg)
        self.assertIn("175.50", msg)


class TestFormatPnlReply(unittest.TestCase):

    def setUp(self):
        self.n = _build_notifier()

    def test_positive_pnl_has_sign(self):
        self.n._realized_pnl = 250.0
        self.n._total_return_pct = 0.025
        msg = self.n._format_pnl_reply()
        self.assertIn("+250.00", msg)
        self.assertIn("2.5000%", msg)

    def test_negative_pnl(self):
        self.n._realized_pnl = -50.0
        self.n._total_return_pct = -0.005
        msg = self.n._format_pnl_reply()
        self.assertIn("-50.00", msg)


# ---------------------------------------------------------------------------
# 4. EventBus handler behaviour
# ---------------------------------------------------------------------------


class TestOnDecisionHoldSuppression(unittest.TestCase):

    def _hold_event(self):
        return _EventStub(
            event_type="intelligence.decision",
            symbol="AAPL",
            action="HOLD",
            confidence=0.5,
            rationale="neutral",
        )

    def test_hold_suppressed_when_notify_hold_false(self):
        n = _build_notifier(notify_hold=False)
        sent = []
        n._schedule_send = lambda t: sent.append(t)
        n._on_decision(self._hold_event())
        self.assertEqual(sent, [])

    def test_hold_sent_when_notify_hold_true(self):
        n = _build_notifier(notify_hold=True)
        sent = []
        n._schedule_send = lambda t: sent.append(t)
        n._on_decision(self._hold_event())
        self.assertEqual(len(sent), 1)


class TestOnFillSchedulesSend(unittest.TestCase):

    def test_fill_event_schedules_send(self):
        n = _build_notifier()
        sent = []
        n._schedule_send = lambda t: sent.append(t)

        ev = _EventStub(
            event_type="execution.fill",
            action="BUY",
            symbol="TSLA",
            quantity=5.0,
            fill_price=200.0,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        n._on_fill(ev)
        self.assertEqual(len(sent), 1)
        self.assertIn("TSLA", sent[0])


class TestOnPortfolioUpdatesCache(unittest.TestCase):

    def test_cache_updated_from_portfolio_event(self):
        n = _build_notifier()
        ev = _EventStub(
            event_type="portfolio.state",
            portfolio_value=50000.0,
            cash=10000.0,
            realized_pnl=500.0,
            total_return_pct=0.01,
            positions=({"symbol": "AAPL", "quantity": 10.0, "entry_price": 150.0},),
        )
        n._on_portfolio(ev)
        self.assertAlmostEqual(n._portfolio_value, 50000.0)
        self.assertAlmostEqual(n._cash, 10000.0)
        self.assertAlmostEqual(n._realized_pnl, 500.0)
        self.assertEqual(len(n._positions), 1)
        self.assertEqual(n._positions[0]["symbol"], "AAPL")


class TestOnSessionEnd(unittest.TestCase):

    def test_session_end_schedules_send(self):
        n = _build_notifier()
        sent = []
        n._schedule_send = lambda t: sent.append(t)

        payload = {
            "total_pnl": 100.0,
            "win_rate": 0.5,
            "total_trades": 4,
            "sharpe_ratio": 1.0,
            "max_drawdown": 0.05,
            "portfolio_value": 10500.0,
        }
        ev = _EventStub(event_type="session.end", payload=payload)
        n._on_session_end(ev)
        self.assertEqual(len(sent), 1)
        self.assertIn("Session Summary", sent[0])


# ---------------------------------------------------------------------------
# 5. Async command handler tests
# ---------------------------------------------------------------------------


class TestAsyncCommandHandlers(unittest.IsolatedAsyncioTestCase):
    """Test async Telegram command handlers using IsolatedAsyncioTestCase."""

    def _make_update(self):
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        return update

    def _make_notifier(self, **kwargs):
        bus = _FakeBus()
        n = _build_notifier(bus=bus, **kwargs)
        n._bus = bus
        return n, bus

    async def test_cmd_status_replies(self):
        n, _ = self._make_notifier()
        n._portfolio_value = 9999.99
        n._cash = 1234.56
        update = self._make_update()
        await n._cmd_status(update, MagicMock())
        update.message.reply_text.assert_awaited_once()
        reply = update.message.reply_text.call_args[0][0]
        self.assertIn("9999.99", reply)
        self.assertIn("1234.56", reply)

    async def test_cmd_positions_no_positions(self):
        n, _ = self._make_notifier()
        n._positions = []
        update = self._make_update()
        await n._cmd_positions(update, MagicMock())
        reply = update.message.reply_text.call_args[0][0]
        self.assertEqual(reply, "No open positions.")

    async def test_cmd_pnl_replies(self):
        n, _ = self._make_notifier()
        n._realized_pnl = 100.0
        n._total_return_pct = 0.01
        update = self._make_update()
        await n._cmd_pnl(update, MagicMock())
        update.message.reply_text.assert_awaited_once()

    async def test_cmd_stop_publishes_before_reply(self):
        """_cmd_stop must publish the shutdown event BEFORE replying."""
        n, bus = self._make_notifier()
        call_order: list = []

        original_publish = bus.publish

        def tracked_publish(ev):
            call_order.append(("publish", ev.event_type))
            return original_publish(ev)

        bus.publish = tracked_publish

        update = self._make_update()

        async def tracked_reply_text(text):
            call_order.append(("reply", text))

        update.message.reply_text = AsyncMock(side_effect=tracked_reply_text)

        await n._cmd_stop(update, MagicMock())

        self.assertGreater(len(call_order), 1)
        self.assertEqual(call_order[0][0], "publish")
        self.assertEqual(call_order[0][1], "system.shutdown_requested")
        self.assertEqual(call_order[1][0], "reply")

    async def test_cmd_stop_reply_contains_shutdown_message(self):
        n, _ = self._make_notifier()
        update = self._make_update()
        await n._cmd_stop(update, MagicMock())
        reply = update.message.reply_text.call_args[0][0]
        self.assertIn("Shutdown requested", reply)
        self.assertIn("gracefully", reply)

    async def test_cmd_stop_no_reply_if_publish_fails(self):
        """If bus.publish raises, no confirmation is sent."""
        n, bus = self._make_notifier()

        def failing_publish(ev):
            raise RuntimeError("bus error")

        bus.publish = failing_publish

        update = self._make_update()
        await n._cmd_stop(update, MagicMock())
        update.message.reply_text.assert_not_awaited()

    async def test_cmd_unknown_lists_all_four_commands(self):
        n, _ = self._make_notifier()
        update = self._make_update()
        await n._cmd_unknown(update, MagicMock())
        reply = update.message.reply_text.call_args[0][0]
        for cmd in ("/status", "/positions", "/pnl", "/stop"):
            self.assertIn(cmd, reply)


# ---------------------------------------------------------------------------
# 6. _safe_send — WARNING log on TelegramError
# ---------------------------------------------------------------------------


class TestSafeSend(unittest.IsolatedAsyncioTestCase):

    def _make_notifier_with_mock_bot(self, bot_side_effect=None):
        n = _build_notifier()
        mock_app = MagicMock()
        mock_bot = AsyncMock()
        if bot_side_effect is not None:
            mock_bot.send_message = AsyncMock(side_effect=bot_side_effect)
        else:
            mock_bot.send_message = AsyncMock(return_value=None)
        mock_app.bot = mock_bot
        n._app = mock_app
        return n, mock_bot

    async def test_telegram_error_logs_warning(self):
        from telegram.error import TelegramError

        n, _ = self._make_notifier_with_mock_bot(
            bot_side_effect=TelegramError("network error")
        )
        with self.assertLogs(
            "dashboard.telegram.telegram_notifier", level="WARNING"
        ) as cm:
            await n._safe_send("test message")
        self.assertTrue(any("Telegram send failed" in m for m in cm.output))

    async def test_successful_send_calls_bot(self):
        n, mock_bot = self._make_notifier_with_mock_bot()
        await n._safe_send("hello")
        mock_bot.send_message.assert_awaited_once_with(chat_id="123456", text="hello")


if __name__ == "__main__":
    unittest.main()
