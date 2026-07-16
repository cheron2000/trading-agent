"""
paper_trading — Paper Trading Validation Harness.

Wires all 7 layers for fixture-based simulation.
No live broker calls — validation only.
"""

from .runner import PaperTradingRunner

__all__ = ("PaperTradingRunner",)
