"""
intelligence.strategies.i_strategy
=====================================

IStrategy Protocol — contract for all trading strategy implementations.

Python Version: 3.11+
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from data.models.feature_vector import FeatureVector
from intelligence.models.decision import Decision


@runtime_checkable
class IStrategy(Protocol):
    """Protocol for trading strategy implementations.

    Strategies are stateless evaluators: given a FeatureVector they
    return a Decision. All state (memory, context) is managed externally.
    """

    @property
    def strategy_id(self) -> str:
        """Return the unique identifier for this strategy."""
        ...

    def evaluate(self, feature_vector: FeatureVector) -> Decision:
        """Evaluate a feature vector and return a trading decision.

        Args:
            feature_vector: Engineered features for a symbol.

        Returns:
            Immutable ``Decision`` with action, confidence, and rationale.

        Raises:
            ValueError: If ``feature_vector`` is None or invalid.
        """
        ...
