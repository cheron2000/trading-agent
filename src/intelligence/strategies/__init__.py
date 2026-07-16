"""intelligence.strategies — Strategy interface and implementations."""

from .i_strategy import IStrategy
from .rule_based import SimpleRuleStrategy

__all__ = ("IStrategy", "SimpleRuleStrategy")
