"""
intelligence.events.decision_event
=====================================

DecisionEvent — published on the EventBus for the Execution Layer.

Consumed by Apollo-Exec for risk checking and order generation.

Python Version: 3.11+
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal

from foundation.base_event import BaseEvent


@dataclass(frozen=True, slots=True)
class DecisionEvent(BaseEvent):
    """Event carrying a trading decision for the Execution Layer.

    Inherits identity fields from BaseEvent.

    Attributes:
        symbol:      Canonical ticker symbol.
        action:      BUY, SELL, or HOLD.
        confidence:  Confidence score in [0.0, 1.0].
        rationale:   Explanation for audit trail.
        strategy_id: Originating strategy identifier.
    """

    symbol: str = ""
    action: Literal["BUY", "SELL", "HOLD"] = "HOLD"
    confidence: float = 0.0
    rationale: str = ""
    strategy_id: str = ""

    _VALID_ACTIONS: ClassVar[frozenset[str]] = frozenset({"BUY", "SELL", "HOLD"})

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must not be empty.")
        if self.action not in self._VALID_ACTIONS:
            raise ValueError(
                f"action must be one of {sorted(self._VALID_ACTIONS)}, "
                f"got: {self.action!r}."
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0.")
        if not self.rationale or not self.rationale.strip():
            raise ValueError("rationale must not be empty.")
        if not self.strategy_id or not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty.")

    def to_dict(self) -> dict[str, object]:
        base = super().to_dict()
        base.update({
            "symbol": self.symbol,
            "action": self.action,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "strategy_id": self.strategy_id,
        })
        return base
