"""
intelligence.models.decision
==============================

Decision — structured output from any strategy or LLM agent.

This is the canonical intelligence output model. It carries the
trading action, confidence score, and rationale for audit purposes.

Python Version: 3.11+
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal


@dataclass(frozen=True, slots=True)
class Decision:
    """Immutable trading decision produced by a strategy or LLM agent.

    Attributes:
        symbol:      Canonical ticker symbol.
        action:      Trading action — BUY, SELL, or HOLD.
        confidence:  Confidence score in [0.0, 1.0].
        rationale:   Human-readable explanation for audit purposes.
        strategy_id: Identifier of the strategy that produced this decision.
    """

    symbol: str
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: float
    rationale: str
    strategy_id: str

    _VALID_ACTIONS: ClassVar[frozenset[str]] = frozenset({"BUY", "SELL", "HOLD"})
    _MAX_SYMBOL_LENGTH: ClassVar[int] = 32
    _MAX_RATIONALE_LENGTH: ClassVar[int] = 2048
    _MAX_STRATEGY_ID_LENGTH: ClassVar[int] = 128

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must not be empty.")
        if len(self.symbol) > self._MAX_SYMBOL_LENGTH:
            raise ValueError("symbol exceeds maximum length.")
        if self.action not in self._VALID_ACTIONS:
            raise ValueError(
                f"action must be one of {sorted(self._VALID_ACTIONS)}, "
                f"got: {self.action!r}."
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0.")
        if not self.rationale or not self.rationale.strip():
            raise ValueError("rationale must not be empty.")
        if len(self.rationale) > self._MAX_RATIONALE_LENGTH:
            raise ValueError("rationale exceeds maximum length.")
        if not self.strategy_id or not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty.")
        if len(self.strategy_id) > self._MAX_STRATEGY_ID_LENGTH:
            raise ValueError("strategy_id exceeds maximum length.")

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "strategy_id": self.strategy_id,
        }

    def __str__(self) -> str:
        return (
            f"Decision(symbol='{self.symbol}', action='{self.action}', "
            f"confidence={self.confidence:.2f}, strategy='{self.strategy_id}')"
        )
