"""
dashboard.telegram.telegram_notifier
=====================================

TelegramNotifier — L7 Dashboard component that mirrors LiveView but over
Telegram. Subscribes to EventBus events and sends formatted alerts to a
configured Telegram chat. Also registers inbound command handlers so an
operator can query portfolio state and trigger graceful shutdown from a
phone.

Threading model
---------------
``python-telegram-bot`` >= 20 is fully async; ``run_hour.py`` is
synchronous. This module solves the mismatch by spinning up a *daemon*
background thread that owns a dedicated asyncio event loop. The bot's
``Application`` polling runs on that loop. EventBus handlers are called
on the main thread; they schedule coroutines onto the bot's loop with
``asyncio.run_coroutine_threadsafe``.

Architecture rule enforced
---------------------------
ZERO imports from ``execution``, ``intelligence``, ``data``, or
``analytics``. All trading data arrives exclusively via EventBus
subscriptions as ``BaseEvent`` instances.

Python Version: 3.11+
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from foundation.base_event import BaseEvent
from communication.interfaces.i_event_bus import IEventBus
from communication.models.subscription import Subscription


_log = logging.getLogger(__name__)


class TelegramNotifier:
    """Telegram-based dashboard notification component (L7).

    Subscribes to four EventBus patterns and forwards alerts to a
    Telegram chat. Registers four bot commands for interactive
    portfolio queries and graceful remote shutdown.

    Attributes
    ----------
    _bus:             Injected EventBus.
    _bot_token:       Telegram Bot API token.
    _chat_id:         Target Telegram chat identifier.
    _notify_hold:     When False, HOLD decisions are suppressed.
    _subscriptions:   Active EventBus subscriptions (cleared on stop).
    _app:             python-telegram-bot Application instance.
    _loop:            Dedicated asyncio loop running in the bot thread.
    _thread:          Daemon thread hosting the bot loop.
    _stop_event:      threading.Event signalled by stop() to halt the loop.

    Portfolio state cache (updated by _on_portfolio):
    _portfolio_value, _cash, _positions, _realized_pnl, _total_return_pct
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        bus: IEventBus,
        bot_token: str,
        chat_id: str,
        notify_hold: bool = False,
    ) -> None:
        """Construct a TelegramNotifier.

        Parameters
        ----------
        bus:          EventBus to subscribe on and publish to.
        bot_token:    Telegram Bot API token from @BotFather.
        chat_id:      Telegram chat ID to send messages to.
        notify_hold:  If True, HOLD decisions are forwarded to Telegram.

        Raises
        ------
        ValueError:
            If ``bot_token`` or ``chat_id`` is empty or whitespace.
        """
        if not bot_token or not bot_token.strip():
            raise ValueError("bot_token must not be empty.")
        if not chat_id or not chat_id.strip():
            raise ValueError("chat_id must not be empty.")

        self._bus: IEventBus = bus
        self._bot_token: str = bot_token
        self._chat_id: str = chat_id
        self._notify_hold: bool = notify_hold
        self._subscriptions: list[Subscription] = []
        self._log: logging.Logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )

        # These are set in start()
        self._app: Application | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event = threading.Event()

        # Portfolio state cache — populated by _on_portfolio()
        self._portfolio_value: float = 0.0
        self._cash: float = 0.0
        self._positions: list[dict] = []
        self._realized_pnl: float = 0.0
        self._total_return_pct: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the Telegram bot and subscribe to EventBus patterns.

        Builds the Application, registers command handlers, subscribes
        to four EventBus patterns, then spins up a daemon thread that
        runs the bot's asyncio event loop.
        """
        # Build Application
        self._app = Application.builder().token(self._bot_token).build()

        # Register command handlers
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("positions", self._cmd_positions))
        self._app.add_handler(CommandHandler("pnl", self._cmd_pnl))
        self._app.add_handler(CommandHandler("stop", self._cmd_stop))
        self._app.add_handler(
            MessageHandler(filters.COMMAND, self._cmd_unknown)
        )

        # Subscribe to EventBus patterns
        self._subscriptions = [
            self._bus.subscribe("execution.fill", self._on_fill),
            self._bus.subscribe("intelligence.decision", self._on_decision),
            self._bus.subscribe("session.end", self._on_session_end),
            self._bus.subscribe("portfolio.state", self._on_portfolio),
        ]

        # Reset the stop signal
        self._stop_event.clear()

        # Spin up dedicated daemon thread with its own asyncio loop
        self._thread = threading.Thread(
            target=self._thread_main,
            daemon=True,
            name="telegram-bot-thread",
        )
        self._thread.start()

        self._log.info("TelegramNotifier started — bot polling thread launched.")

    def stop(self) -> None:
        """Stop the Telegram bot and unsubscribe from all EventBus patterns.

        Signals the bot thread to halt, waits for it to finish, then
        removes all EventBus subscriptions.
        """
        # Signal the asyncio loop to stop
        self._stop_event.set()

        # If the loop is running, schedule a graceful application stop
        if self._loop is not None and self._loop.is_running() and self._app is not None:
            future = asyncio.run_coroutine_threadsafe(
                self._shutdown_app(), self._loop
            )
            try:
                future.result(timeout=10)
            except Exception as exc:  # noqa: BLE001
                self._log.warning("Error during bot shutdown: %s", exc)

        # Join the thread
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=15)

        # Unsubscribe all EventBus patterns
        for sub in self._subscriptions:
            self._bus.unsubscribe(sub)
        self._subscriptions.clear()

        self._log.info("TelegramNotifier stopped.")

    # ------------------------------------------------------------------
    # Background thread entry-point
    # ------------------------------------------------------------------

    def _thread_main(self) -> None:
        """Entry-point for the background daemon thread.

        Creates a dedicated asyncio event loop, stores a reference so
        that main-thread handlers can schedule coroutines onto it, then
        runs the bot coroutine until completion.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._run_bot())
        except Exception as exc:  # noqa: BLE001
            self._log.critical("Bot thread crashed: %s", exc, exc_info=True)
        finally:
            loop.close()

    async def _run_bot(self) -> None:
        """Coroutine that runs the bot Application until stop() is called."""
        app = self._app
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        try:
            # Block until stop_event is set by stop()
            while not self._stop_event.is_set():
                await asyncio.sleep(0.5)
        finally:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()

    async def _shutdown_app(self) -> None:
        """Gracefully shut down the Application from within its own loop."""
        # The _run_bot loop will notice _stop_event and handle shutdown;
        # this is a no-op placeholder for any extra teardown needed.
        pass

    # ------------------------------------------------------------------
    # EventBus handlers (called on main thread)
    # ------------------------------------------------------------------

    def _on_fill(self, event: BaseEvent) -> None:
        """Handle execution.fill events and send a trade alert."""
        try:
            action = getattr(event, "action", "BUY")
            symbol = getattr(event, "symbol", "")
            fill_price = getattr(event, "fill_price", 0.0)
            quantity = getattr(event, "quantity", 0.0)

            # Compute realized P&L for SELL orders
            realized_pnl: float | None = None
            if action == "SELL":
                entry_price = self._find_entry_price(symbol, fill_price)
                realized_pnl = (fill_price - entry_price) * quantity

            # Update entry price cache for BUY orders
            if action == "BUY":
                self._entry_prices_cache()[symbol] = fill_price

            text = self._format_fill_message(event, realized_pnl)
            self._schedule_send(text)
        except Exception as exc:  # noqa: BLE001
            self._log.error("_on_fill handler error: %s", exc, exc_info=True)

    def _on_decision(self, event: BaseEvent) -> None:
        """Handle intelligence.decision events and send a decision digest."""
        try:
            action = getattr(event, "action", "HOLD")
            if action == "HOLD" and not self._notify_hold:
                return
            text = self._format_decision_message(event)
            self._schedule_send(text)
        except Exception as exc:  # noqa: BLE001
            self._log.error("_on_decision handler error: %s", exc, exc_info=True)

    def _on_session_end(self, event: BaseEvent) -> None:
        """Handle session.end events and send a session summary."""
        try:
            payload = getattr(event, "payload", {}) or {}
            text = self._format_session_summary(payload)
            self._schedule_send(text)
        except Exception as exc:  # noqa: BLE001
            self._log.error("_on_session_end handler error: %s", exc, exc_info=True)

    def _on_portfolio(self, event: BaseEvent) -> None:
        """Handle portfolio.state events and update the in-memory cache."""
        self._portfolio_value = getattr(event, "portfolio_value", 0.0)
        self._cash = getattr(event, "cash", 0.0)
        raw_positions = getattr(event, "positions", ())
        self._positions = list(raw_positions) if raw_positions else []
        self._realized_pnl = getattr(event, "realized_pnl", 0.0)
        self._total_return_pct = getattr(event, "total_return_pct", 0.0)

    # ------------------------------------------------------------------
    # Telegram command handlers (async, called by python-telegram-bot)
    # ------------------------------------------------------------------

    async def _cmd_status(
        self, update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Reply to /status with portfolio value and cash."""
        text = self._format_status_reply()
        await update.message.reply_text(text)

    async def _cmd_positions(
        self, update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Reply to /positions with open positions list."""
        text = self._format_positions_reply()
        await update.message.reply_text(text)

    async def _cmd_pnl(
        self, update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Reply to /pnl with realized P&L and total return."""
        text = self._format_pnl_reply()
        await update.message.reply_text(text)

    async def _cmd_stop(
        self, update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /stop: publish shutdown event then confirm to user."""
        try:
            self._bus.publish(
                BaseEvent(event_type="system.shutdown_requested")
            )
        except Exception as exc:  # noqa: BLE001
            self._log.error(
                "Failed to publish system.shutdown_requested: %s", exc,
                exc_info=True,
            )
            # Do not send confirmation if publish failed
            return
        await update.message.reply_text(
            "Shutdown requested. System will stop gracefully."
        )

    async def _cmd_unknown(
        self, update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Reply with help text for any unrecognised command."""
        help_text = (
            "Unknown command. Available commands:\n"
            "/status     — Portfolio value and cash balance\n"
            "/positions  — Open positions with quantity and entry price\n"
            "/pnl        — Realized P&L and total return percentage\n"
            "/stop       — Request graceful system shutdown"
        )
        await update.message.reply_text(help_text)

    # ------------------------------------------------------------------
    # Safe async send helper
    # ------------------------------------------------------------------

    async def _safe_send(self, text: str) -> None:
        """Send a Telegram message; log WARNING on TelegramError.

        If the logger itself raises, the exception is re-raised so that
        the caller can decide how to handle it.

        Parameters
        ----------
        text: Message text to send.
        """
        try:
            bot = self._app.bot
            await bot.send_message(chat_id=self._chat_id, text=text)
        except TelegramError as exc:
            self._log.warning("Telegram send failed: %s", exc)
        except Exception as exc:  # noqa: BLE001
            self._log.warning("Unexpected error sending Telegram message: %s", exc)

    # ------------------------------------------------------------------
    # Message formatters (pure — no I/O)
    # ------------------------------------------------------------------

    def _format_fill_message(
        self,
        event: BaseEvent,
        realized_pnl: float | None,
    ) -> str:
        """Format a trade fill alert.

        BUY: symbol, qty(4dp), price(2dp), timestamp.
        SELL: adds P&L(2dp with sign).
        """
        symbol = getattr(event, "symbol", "")
        action = getattr(event, "action", "BUY")
        quantity = getattr(event, "quantity", 0.0)
        fill_price = getattr(event, "fill_price", 0.0)
        timestamp = getattr(event, "timestamp", None)
        ts_str = timestamp.isoformat() if timestamp is not None else "N/A"

        lines = [
            f"✅ Trade Fill — {action}",
            f"Symbol:    {symbol}",
            f"Qty:       {quantity:.4f}",
            f"Price:     {fill_price:.2f}",
            f"Time:      {ts_str}",
        ]

        if action == "SELL" and realized_pnl is not None:
            sign = "+" if realized_pnl >= 0 else ""
            lines.append(f"P&L:       {sign}{realized_pnl:.2f}")

        return "\n".join(lines)

    def _format_decision_message(self, event: BaseEvent) -> str:
        """Format an AI decision digest.

        Contains symbol, action, confidence(2dp), rationale[:200].
        """
        symbol = getattr(event, "symbol", "")
        action = getattr(event, "action", "HOLD")
        confidence = getattr(event, "confidence", 0.0)
        rationale = getattr(event, "rationale", "")
        rationale_trunc = rationale[:200]

        return (
            f"🤖 Decision Digest\n"
            f"Symbol:     {symbol}\n"
            f"Action:     {action}\n"
            f"Confidence: {confidence:.2f}\n"
            f"Rationale:  {rationale_trunc}"
        )

    def _format_session_summary(self, payload_dict: dict[str, Any]) -> str:
        """Format a session end summary from the payload dictionary.

        Five metrics with correct precision. When total_trades == 0
        returns a "no trades" message with portfolio value.
        """
        total_pnl = payload_dict.get("total_pnl", 0.0)
        win_rate = payload_dict.get("win_rate", 0.0)
        total_trades = payload_dict.get("total_trades", 0)
        sharpe_ratio = payload_dict.get("sharpe_ratio", 0.0)
        max_drawdown = payload_dict.get("max_drawdown", 0.0)
        portfolio_value = payload_dict.get("portfolio_value", 0.0)

        if total_trades == 0:
            return (
                f"📊 Session Summary\n"
                f"No trades were executed this session.\n"
                f"Portfolio value: {portfolio_value:.2f}"
            )

        pnl_sign = "+" if total_pnl >= 0 else ""
        return (
            f"📊 Session Summary\n"
            f"Total P&L:    {pnl_sign}{total_pnl:.2f}\n"
            f"Win Rate:     {win_rate * 100:.1f}%\n"
            f"Total Trades: {int(total_trades)}\n"
            f"Sharpe:       {sharpe_ratio:.4f}\n"
            f"Max Drawdown: {max_drawdown * 100:.4f}%"
        )

    def _format_status_reply(self) -> str:
        """Format /status reply from in-memory cache."""
        return (
            f"📈 Portfolio Status\n"
            f"Value: {self._portfolio_value:.2f}\n"
            f"Cash:  {self._cash:.2f}"
        )

    def _format_positions_reply(self) -> str:
        """Format /positions reply from in-memory cache."""
        if not self._positions:
            return "No open positions."

        lines = ["📋 Open Positions"]
        for pos in self._positions:
            symbol = pos.get("symbol", "")
            quantity = pos.get("quantity", 0.0)
            entry_price = pos.get("entry_price", 0.0)
            lines.append(
                f"{symbol}: qty={quantity:.4f}, entry={entry_price:.2f}"
            )
        return "\n".join(lines)

    def _format_pnl_reply(self) -> str:
        """Format /pnl reply from in-memory cache."""
        sign = "+" if self._realized_pnl >= 0 else ""
        return (
            f"💰 P&L Summary\n"
            f"Realized P&L:  {sign}{self._realized_pnl:.2f}\n"
            f"Total Return:  {self._total_return_pct * 100:.4f}%"
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _schedule_send(self, text: str) -> None:
        """Schedule _safe_send on the bot's event loop (thread-safe)."""
        if self._loop is None or not self._loop.is_running():
            self._log.warning(
                "Cannot send message — bot loop not running: %s",
                text[:80],
            )
            return
        asyncio.run_coroutine_threadsafe(self._safe_send(text), self._loop)

    def _entry_prices_cache(self) -> dict[str, float]:
        """Lazy-initialise the entry price cache for SELL P&L computation."""
        if not hasattr(self, "_entry_prices"):
            # Use object.__setattr__ since the class is not frozen
            object.__setattr__(self, "_entry_prices", {})
        return self._entry_prices  # type: ignore[attr-defined]

    def _find_entry_price(self, symbol: str, fill_price: float) -> float:
        """Return cached entry price for a symbol, or fill_price if unknown."""
        return self._entry_prices_cache().get(symbol, fill_price)
