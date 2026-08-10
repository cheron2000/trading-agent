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
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
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

    def __init__(self, persist_path: str | Path | None = None) -> None:
        """
        Args:
            persist_path:
                Optional path to a JSONL file. If provided, every
                ``record()`` call appends the new entry to this file
                immediately (flushed + fsynced) before returning, so
                a crash right after a fill still leaves a durable,
                replayable audit trail on disk. Defaults to None
                (pure in-memory, no I/O — existing behavior).
        """
        self._entries: list[JournalEntry] = []
        self._persist_path: Path | None = (
            Path(persist_path) if persist_path is not None else None
        )
        if self._persist_path is not None:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)

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
        prev_hash = self._entries[-1].entry_hash if self._entries else self.GENESIS_HASH
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
        if self._persist_path is not None:
            self._append_to_disk(entry)
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

    @classmethod
    def load_from_file(cls, path: str | Path) -> TradeJournal:
        """Reconstruct a TradeJournal by replaying a persisted JSONL file.

        Lets a resumed session extend the same durable hash chain
        instead of starting over at genesis, and lets verify_integrity()
        check the full persisted history — not just what's been
        recorded in the current process's lifetime.

        Args:
            path: Path to a JSONL file previously written by this class.
                  If it doesn't exist yet, returns an empty journal that
                  will create the file on first ``record()``.

        Returns:
            A ``TradeJournal`` with all persisted entries loaded and
            ``persist_path`` set to ``path``, so further ``record()``
            calls keep appending to the same file.

        Raises:
            ValueError: If a line in the file is malformed.
        """
        path = Path(path)
        journal = cls(persist_path=path)
        if not path.exists():
            return journal

        with path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    fill_data = data["fill"]
                    fill = FillEvent(
                        event_type=fill_data["event_type"],
                        event_id=fill_data["event_id"],
                        occurred_at=datetime.fromisoformat(fill_data["occurred_at"]),
                        schema_version=fill_data["schema_version"],
                        correlation_id=fill_data["correlation_id"],
                        causation_id=fill_data["causation_id"],
                        order_id=fill_data["order_id"],
                        symbol=fill_data["symbol"],
                        action=fill_data["action"],
                        quantity=fill_data["quantity"],
                        fill_price=fill_data["fill_price"],
                        timestamp=datetime.fromisoformat(fill_data["fill_timestamp"]),
                    )
                    entry = JournalEntry(
                        sequence=data["sequence"],
                        timestamp=datetime.fromisoformat(data["timestamp"]),
                        fill=fill,
                        decision_id=data["decision_id"],
                        strategy_id=data["strategy_id"],
                        entry_hash=data["entry_hash"],
                        prev_hash=data["prev_hash"],
                    )
                except (KeyError, ValueError, TypeError) as exc:
                    raise ValueError(
                        f"Malformed journal entry at {path}:{line_no}: {exc}"
                    ) from exc
                journal._entries.append(entry)

        return journal

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append_to_disk(self, entry: JournalEntry) -> None:
        """Append one entry as a JSON line, flushed and fsynced.

        This is a write-ahead style append: the entry is durably on
        disk before ``record()`` returns, so a crash immediately after
        a fill still leaves an audit trail instead of losing it.
        """
        if self._persist_path is None:
            raise RuntimeError("persist_path is not configured")
        line = json.dumps(entry.to_dict(), sort_keys=True)
        with self._persist_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())

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
