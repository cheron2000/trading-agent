"""
intelligence.strategies.rule_based
=====================================

SimpleRuleStrategy — threshold-based rule strategy.

Rule:
    price_change_pct > +threshold  → BUY
    price_change_pct < -threshold  → SELL
    otherwise                      → HOLD

Confidence = min(abs(price_change_pct) / threshold, 1.0)
For HOLD: confidence = max(0.0, 1.0 - abs(price_change_pct) / threshold)

Python Version: 3.11+
"""

from __future__ import annotations

from typing import ClassVar, Literal

from data.models.feature_vector import FeatureVector
from intelligence.models.decision import Decision
from intelligence.strategies.i_strategy import IStrategy


class SimpleRuleStrategy:
    """Threshold-based rule strategy implementing IStrategy.

    Evaluates ``price_change_pct`` from the feature vector against
    a configurable threshold to produce BUY, SELL, or HOLD decisions.
    """

    DEFAULT_THRESHOLD: ClassVar[float] = 1.0
    STRATEGY_ID_PREFIX: ClassVar[str] = "simple-rule"

    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        """
        Args:
            threshold:
                Minimum absolute ``price_change_pct`` to trigger
                BUY or SELL. Must be > 0.

        Raises:
            ValueError: If ``threshold`` is zero or negative.
        """
        if threshold <= 0:
            raise ValueError("threshold must be greater than zero.")
        self._threshold = threshold

    # ------------------------------------------------------------------
    # IStrategy implementation
    # ------------------------------------------------------------------

    @property
    def strategy_id(self) -> str:
        """Return the unique strategy identifier."""
        return f"{self.STRATEGY_ID_PREFIX}-t{self._threshold}"

    def evaluate(self, feature_vector: FeatureVector) -> Decision:
        """Evaluate a feature vector using the price-change-pct rule.

        Args:
            feature_vector: Engineered features. Must contain
                            ``price_change_pct``.

        Returns:
            Immutable ``Decision``.

        Raises:
            ValueError: If ``feature_vector`` is None or missing
                        ``price_change_pct``.
        """
        if feature_vector is None:
            raise ValueError("feature_vector must not be None.")

        if "price_change_pct" not in feature_vector.features:
            raise ValueError(
                "feature_vector must contain 'price_change_pct'."
            )

        pct = feature_vector.features["price_change_pct"]
        action: Literal["BUY", "SELL", "HOLD"]

        if pct > self._threshold:
            action = "BUY"
            confidence = min(abs(pct) / self._threshold, 1.0)
            rationale = (
                f"price_change_pct={pct:.2f}% exceeds threshold "
                f"+{self._threshold}% — bullish signal."
            )
        elif pct < -self._threshold:
            action = "SELL"
            confidence = min(abs(pct) / self._threshold, 1.0)
            rationale = (
                f"price_change_pct={pct:.2f}% below threshold "
                f"-{self._threshold}% — bearish signal."
            )
        else:
            action = "HOLD"
            confidence = max(
                0.0, 1.0 - abs(pct) / self._threshold
            )
            rationale = (
                f"price_change_pct={pct:.2f}% within threshold "
                f"±{self._threshold}% — no signal."
            )

        return Decision(
            symbol=feature_vector.symbol,
            action=action,
            confidence=round(confidence, 6),
            rationale=rationale,
            strategy_id=self.strategy_id,
        )


# Runtime protocol check
assert isinstance(SimpleRuleStrategy(), IStrategy), (
    "SimpleRuleStrategy does not satisfy the IStrategy Protocol."
)
