"""
analytics.journal.trade_journal
=================================

TradeJournal — append-only trade log with hash-chain tamper evidence.

Each entry is hashed with the previous entry's hash to form a chain.
Any modification to a prior entry breaks all subsequent hashes,
making tampering detectable.

Python Version: 3.11+
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar

from execution.events.fill_event import FillEvent
from intelligence.events.decision_event import DecisionEvent


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """Immutable, hash-chained journal entry.

    Attributes:
        sequence:       Monotonically increasing entry number.
        timestamp:      UTC time the entry was recorded.
        fill:           The fill that triggered this entry.
        decision_id:    event_id of the originating DecisionEvent.
        strategy_id:    Strategy that produced the decision.
        entry_hash:     SHA-256 of this entry's content.
        prev_hash:      SHA-256 of the previous entry (genesis = "0"*64).
    """

    sequence: int
    timestamp: datetime
    fill: FillEvent
    decision_id: str
    strategy_id: str
    entry_hash: str
    prev_hash: str

    def to_dict(self) -> dict[str, object]:
        ts = self.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return {
            "sequence": self.sequence,
            "timestamp": ts.isoformat(),
            "fill": self.fill.to_dict(),
            "decision_id": self.decision_id,
            "strategy_id": self.strategy_id,
            "entry_hash": self.entry_hash,
            "prev_hash": self.prev_hash,
        }


class TradeJournal:
    """Append-only, hash-chained trade journal.

    Usage::

        journal = TradeJournal()
        journal.record(fill, decision)
        entries = journal.entries()
        ok = journal.verify_integrity()
    """

    GENESIS_HASH: ClassVar[str] = "0" * 64

    def __init__(self) -> None:
        self._entries: list[JournalEntry] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(self, fill: FillEvent, decision: DecisionEvent) -> JournalEntry:
        """Append a new entry for a fill + decision pair.

        Args:
            fill:     The executed FillEvent.
            decision: The DecisionEvent that triggered the trade.

        Returns:
            The newly created, immutable ``JournalEntry``.

        Raises:
            ValueError: If fill or decision is None.
        """
        if fill is None:
            raise ValueError("fill must not be None.")
        if decision is None:
            raise ValueError("decision must not be None.")

        sequence = len(self._entries) + 1
        prev_hash = (
            self._entries[-1].entry_hash
            if self._entries
            else self.GENESIS_HASH
        )
        now = datetime.now(timezone.utc)

        entry_hash = self._compute_hash(
            sequence=sequence,
            timestamp=now,
            fill=fill,
            decision_id=decision.event_id,
            strategy_id=decision.strategy_id,
            prev_hash=prev_hash,
        )

        entry = JournalEntry(
            sequence=sequence,
            timestamp=now,
            fill=fill,
            decision_id=decision.event_id,
            strategy_id=decision.strategy_id,
            entry_hash=entry_hash,
            prev_hash=prev_hash,
        )
        self._entries.append(entry)
        return entry

    def entries(self) -> list[JournalEntry]:
        """Return all journal entries in sequence order."""
        return list(self._entries)

    def verify_integrity(self) -> bool:
        """Verify the hash chain is unbroken.

        Returns:
            True if every entry's prev_hash matches the previous
            entry's entry_hash (or genesis for the first entry).
        """
        expected_prev = self.GENESIS_HASH
        for entry in self._entries:
            if entry.prev_hash != expected_prev:
                return False
            # Recompute and check this entry's hash
            recomputed = self._compute_hash(
                sequence=entry.sequence,
                timestamp=entry.timestamp,
                fill=entry.fill,
                decision_id=entry.decision_id,
                strategy_id=entry.strategy_id,
                prev_hash=entry.prev_hash,
            )
            if recomputed != entry.entry_hash:
                return False
            expected_prev = entry.entry_hash
        return True

    @property
    def entry_count(self) -> int:
        """Return the number of recorded entries."""
        return len(self._entries)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_hash(
        sequence: int,
        timestamp: datetime,
        fill: FillEvent,
        decision_id: str,
        strategy_id: str,
        prev_hash: str,
    ) -> str:
        """Compute a deterministic SHA-256 hash for an entry."""
        ts = timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        payload = json.dumps(
            {
                "sequence": sequence,
                "timestamp": ts.isoformat(),
                "order_id": fill.order_id,
                "symbol": fill.symbol,
                "action": fill.action,
                "quantity": fill.quantity,
                "fill_price": fill.fill_price,
                "decision_id": decision_id,
                "strategy_id": strategy_id,
                "prev_hash": prev_hash,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
