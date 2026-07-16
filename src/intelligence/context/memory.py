"""
intelligence.context.memory
=============================

DecisionMemory — rolling window of past decisions for context injection.

Provides recent decision history to the LLM agent or strategy context.
Uses a bounded deque for O(1) append with automatic eviction.

Python Version: 3.11+
"""

from __future__ import annotations

from collections import deque
from typing import ClassVar

from intelligence.models.decision import Decision


class DecisionMemory:
    """Rolling window store for recent trading decisions.

    Thread-safety note: this class is NOT thread-safe by design.
    If concurrent access is needed, wrap in a lock at the call site.

    Usage::

        memory = DecisionMemory(max_size=100)
        memory.add(decision)
        last_five = memory.recent(5)
    """

    DEFAULT_MAX_SIZE: ClassVar[int] = 100

    def __init__(self, max_size: int = DEFAULT_MAX_SIZE) -> None:
        """
        Args:
            max_size: Maximum number of decisions to retain.
                      Must be >= 1.

        Raises:
            ValueError: If ``max_size`` is less than 1.
        """
        if max_size < 1:
            raise ValueError("max_size must be at least 1.")
        self._max_size = max_size
        self._store: deque[Decision] = deque(maxlen=max_size)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, decision: Decision) -> None:
        """Append a decision to the memory window.

        If the window is full the oldest entry is automatically evicted.

        Args:
            decision: Immutable ``Decision`` to store.

        Raises:
            ValueError: If ``decision`` is None.
        """
        if decision is None:
            raise ValueError("decision must not be None.")
        self._store.append(decision)

    def recent(self, n: int = 5) -> list[Decision]:
        """Return the most recent n decisions (oldest first).

        Args:
            n: Number of decisions to return. Clamped to available size.

        Returns:
            List of up to ``n`` most recent decisions.

        Raises:
            ValueError: If ``n`` is less than 1.
        """
        if n < 1:
            raise ValueError("n must be at least 1.")
        items = list(self._store)
        return items[-n:]

    def clear(self) -> None:
        """Remove all stored decisions."""
        self._store.clear()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        """Return current number of stored decisions."""
        return len(self._store)

    @property
    def max_size(self) -> int:
        """Return the configured maximum window size."""
        return self._max_size

    @property
    def is_empty(self) -> bool:
        """Return True if no decisions are stored."""
        return len(self._store) == 0
