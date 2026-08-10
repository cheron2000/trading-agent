"""
intelligence.memory.trade_memory
==================================

Trade Memory — persistent self-reflection engine for ATLAS.

Stores completed trade outcomes (symbol, entry/exit prices, PnL%,
rationale, win/loss tag) in a JSON-lines memory bank so the LLM
can learn from recent wins and losses for each symbol.

Python Version: 3.11+
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# Default path for the trade memory store
_DEFAULT_MEMORY_PATH = (
    Path(__file__).resolve().parents[3]
    / "data_store"
    / "memory"
    / "trade_reflections.jsonl"
)


class TradeMemory:
    """Persistent trade memory for ATLAS self-reflection.

    Each completed round-trip trade is stored as a JSON-lines entry with:
    - symbol, entry_price, exit_price, pnl_pct, pnl_usd
    - action_taken (BUY/SELL), rationale, outcome (WIN/LOSS)
    - key_indicators at entry time (RSI, regime, etc.)
    - lesson: auto-generated one-liner summary
    """

    def __init__(self, memory_path: Path | str | None = None) -> None:
        self._path = Path(memory_path) if memory_path else _DEFAULT_MEMORY_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        """Load existing memory entries from disk."""
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._entries.append(json.loads(line))
            _log.info(
                "Loaded %d trade reflections from %s", len(self._entries), self._path
            )
        except Exception as exc:
            _log.warning("Failed to load trade memory from %s: %s", self._path, exc)

    def record_trade(
        self,
        symbol: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
        entry_rationale: str = "",
        exit_rationale: str = "",
        entry_indicators: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a completed round-trip trade.

        Args:
            symbol: Trading symbol (e.g., 'MSFT', 'BTC-USD').
            entry_price: Price at which position was opened.
            exit_price: Price at which position was closed.
            quantity: Number of shares/units traded.
            entry_rationale: LLM rationale at entry time.
            exit_rationale: LLM rationale or trigger at exit time.
            entry_indicators: Key indicators at entry (RSI, regime, etc.).

        Returns:
            The recorded memory entry dict.
        """
        pnl_pct = (
            ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0
        )
        pnl_usd = (exit_price - entry_price) * quantity
        outcome = "WIN" if pnl_pct > 0 else "LOSS"

        # Auto-generate lesson
        indicators = entry_indicators or {}
        rsi = indicators.get("rsi", "N/A")
        regime = indicators.get("regime_label", "N/A")

        if outcome == "WIN":
            lesson = (
                f"Profitable trade on {symbol}: entered at ${entry_price:.2f} "
                f"(RSI={rsi}, regime={regime}), exited at ${exit_price:.2f} for +{pnl_pct:.1f}%. "
                f"Setup was confirmed by {exit_rationale[:80] if exit_rationale else 'profit target'}."
            )
        else:
            lesson = (
                f"Losing trade on {symbol}: entered at ${entry_price:.2f} "
                f"(RSI={rsi}, regime={regime}), exited at ${exit_price:.2f} for {pnl_pct:.1f}%. "
                f"Exit trigger: {exit_rationale[:80] if exit_rationale else 'stop-loss'}. "
                f"Avoid similar entries when conditions repeat."
            )

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "entry_price": round(entry_price, 4),
            "exit_price": round(exit_price, 4),
            "quantity": round(quantity, 6),
            "pnl_pct": round(pnl_pct, 2),
            "pnl_usd": round(pnl_usd, 4),
            "outcome": outcome,
            "entry_rationale": entry_rationale[:200],
            "exit_rationale": exit_rationale[:200],
            "indicators": {
                k: round(v, 4) if isinstance(v, float) else v
                for k, v in indicators.items()
            },
            "lesson": lesson,
        }

        self._entries.append(entry)
        self._persist(entry)
        _log.info("Recorded %s trade for %s: %+.2f%%", outcome, symbol, pnl_pct)
        return entry

    def get_reflections(self, symbol: str, limit: int = 3) -> list[dict[str, Any]]:
        """Get the most recent trade reflections for a symbol.

        Args:
            symbol: Trading symbol to query.
            limit: Max number of reflections to return.

        Returns:
            List of recent trade memory entries for the symbol.
        """
        sym_entries = [e for e in self._entries if e.get("symbol") == symbol]
        return sym_entries[-limit:]

    def format_for_prompt(self, symbol: str, limit: int = 3) -> str:
        """Format trade reflections as a text block for injection into LLM prompts.

        Args:
            symbol: Trading symbol.
            limit: Max reflections.

        Returns:
            Human-readable text block, or empty string if no history.
        """
        reflections = self.get_reflections(symbol, limit)
        if not reflections:
            return ""

        lines = [f"== TRADE MEMORY ({symbol}) =="]
        for r in reflections:
            lines.append(
                f"  [{r['outcome']}] {r['symbol']} "
                f"entry=${r['entry_price']:.2f} -> exit=${r['exit_price']:.2f} "
                f"({r['pnl_pct']:+.1f}%)"
            )
            lines.append(f"    Lesson: {r['lesson'][:150]}")
        lines.append(
            "Use these lessons to calibrate your confidence for the current setup."
        )
        return "\n".join(lines)

    def get_stats(self, symbol: str | None = None) -> dict[str, Any]:
        """Get aggregate statistics for trade memory.

        Args:
            symbol: Optional filter by symbol. None for all.

        Returns:
            Dict with total_trades, wins, losses, win_rate, avg_pnl_pct.
        """
        entries = (
            [e for e in self._entries if e.get("symbol") == symbol]
            if symbol
            else self._entries
        )
        if not entries:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "avg_pnl_pct": 0.0,
            }

        wins = sum(1 for e in entries if e.get("outcome") == "WIN")
        losses = len(entries) - wins
        avg_pnl = sum(e.get("pnl_pct", 0) for e in entries) / len(entries)
        return {
            "total_trades": len(entries),
            "wins": wins,
            "losses": losses,
            "win_rate": wins / len(entries) if entries else 0.0,
            "avg_pnl_pct": round(avg_pnl, 2),
        }

    def _persist(self, entry: dict[str, Any]) -> None:
        """Append a single entry to the memory file."""
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            _log.warning("Failed to persist trade memory: %s", exc)

    @property
    def total_entries(self) -> int:
        return len(self._entries)
