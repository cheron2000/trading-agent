"""
execution.models.portfolio
============================

Portfolio — mutable cash + positions tracker.

This is the only mutable model in the Execution layer. It is
intentionally NOT a frozen dataclass because positions change on
every fill. Thread-safety via threading.Lock.

Python Version: 3.11+
"""

from __future__ import annotations

import threading


class Portfolio:
    """Mutable portfolio state: cash balance + open positions.

    Positions are stored as (quantity, avg_entry_price) tuples keyed
    by symbol. All mutations happen through apply_buy / apply_sell.

    Thread-safe via an internal Lock.
    """

    def __init__(self, initial_cash: float = 100_000.0) -> None:
        """
        Args:
            initial_cash: Starting cash balance. Must be >= 0.

        Raises:
            ValueError: If initial_cash is negative.
        """
        if initial_cash < 0:
            raise ValueError("initial_cash must not be negative.")
        self._cash: float = initial_cash
        # symbol → (quantity, avg_entry_price)
        self._positions: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def cash(self) -> float:
        """Current cash balance."""
        with self._lock:
            return self._cash

    def get_position(self, symbol: str) -> tuple[float, float] | None:
        """Return (quantity, avg_entry_price) for symbol, or None."""
        with self._lock:
            return self._positions.get(symbol)

    def all_positions(self) -> dict[str, tuple[float, float]]:
        """Return a snapshot of all positions."""
        with self._lock:
            return dict(self._positions)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def apply_buy(
        self, symbol: str, quantity: float, price: float
    ) -> None:
        """Apply a BUY fill — deduct cash, update position.

        Args:
            symbol:   Ticker symbol.
            quantity: Units bought. Must be > 0.
            price:    Fill price. Must be > 0.

        Raises:
            ValueError: On invalid arguments or insufficient cash.
        """
        if quantity <= 0:
            raise ValueError("quantity must be > 0.")
        if price <= 0:
            raise ValueError("price must be > 0.")

        cost = quantity * price
        with self._lock:
            if cost > self._cash:
                raise ValueError(
                    f"Insufficient cash: need {cost:.2f}, have {self._cash:.2f}."
                )
            self._cash -= cost
            existing = self._positions.get(symbol, (0.0, 0.0))
            old_qty, old_avg = existing
            new_qty = old_qty + quantity
            new_avg = (
                (old_qty * old_avg + quantity * price) / new_qty
                if new_qty > 0
                else 0.0
            )
            self._positions[symbol] = (new_qty, new_avg)

    def apply_sell(
        self, symbol: str, quantity: float, price: float
    ) -> None:
        """Apply a SELL fill — add cash, reduce position.

        Args:
            symbol:   Ticker symbol.
            quantity: Units sold. Must be > 0.
            price:    Fill price. Must be > 0.

        Raises:
            ValueError: On invalid arguments or insufficient position.
        """
        if quantity <= 0:
            raise ValueError("quantity must be > 0.")
        if price <= 0:
            raise ValueError("price must be > 0.")

        with self._lock:
            existing = self._positions.get(symbol, (0.0, 0.0))
            old_qty, old_avg = existing
            if quantity > old_qty + 1e-9:
                raise ValueError(
                    f"Insufficient position in {symbol}: "
                    f"have {old_qty}, need {quantity}."
                )
            proceeds = quantity * price
            self._cash += proceeds
            new_qty = old_qty - quantity
            if new_qty < 1e-9:
                self._positions.pop(symbol, None)
            else:
                self._positions[symbol] = (new_qty, old_avg)

    def portfolio_value(self, price_feed: dict[str, float]) -> float:
        """Return total portfolio value: cash + mark-to-market positions.

        Args:
            price_feed: dict mapping symbol → current price.

        Returns:
            Total float value.
        """
        with self._lock:
            total = self._cash
            for symbol, (qty, _) in self._positions.items():
                price = price_feed.get(symbol, 0.0)
                total += qty * price
            return total
