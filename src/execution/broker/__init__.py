"""
execution.broker
================

Live broker execution components for the AI Trading OS.

Provides drop-in replacements for the paper-trading OrderManager
that submit real orders to external broker APIs.

Python: 3.11+
"""

from execution.broker.alpaca_order_manager import AlpacaOrderManager

__all__ = ["AlpacaOrderManager"]
