"""
communication.bus.scheduler
=============================

Concrete thread-based recurring Scheduler implementation.

Implements the IScheduler Protocol. Used by the Communication Layer
to emit periodic heartbeats and schedule health-check ticks.

Design constraints:
- No imports from layers above Communication.
- Each job runs in its own daemon thread.
- Cancellation is cooperative via threading.Event.

Python Version: 3.11+
"""

from __future__ import annotations

import logging
import threading
from typing import Callable
from uuid import uuid4

_log = logging.getLogger(__name__)

from communication.interfaces.i_scheduler import IScheduler


class _ScheduledJob:
    """Internal representation of a single scheduled job."""

    def __init__(
        self,
        job_id: str,
        interval_seconds: float,
        callback: Callable[[], None],
    ) -> None:
        self.job_id = job_id
        self.interval_seconds = interval_seconds
        self.callback = callback
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"scheduler-{job_id}",
            daemon=True,
        )

    def start(self) -> None:
        """Start the recurring job thread."""
        self._thread.start()

    def cancel(self) -> None:
        """Signal the job to stop after its current wait."""
        self._stop_event.set()

    def _run(self) -> None:
        """Thread entry point — fires callback repeatedly."""
        while not self._stop_event.wait(timeout=self.interval_seconds):
            try:
                self.callback()
            except Exception:
                _log.exception(
                    "Scheduler callback raised an unhandled exception "
                    "(job_id=%s)", self.job_id
                )


class Scheduler:
    """Thread-based recurring callback scheduler.

    Implements ``IScheduler``. Each scheduled job runs in its own
    daemon thread and fires its callback at the specified interval
    until explicitly cancelled.

    Thread safety is ensured via a single lock protecting the job
    registry.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, _ScheduledJob] = {}

    # ------------------------------------------------------------------
    # IScheduler implementation
    # ------------------------------------------------------------------

    def schedule(
        self,
        interval_seconds: float,
        callback: Callable[[], None],
    ) -> str:
        """Schedule a recurring callback.

        Args:
            interval_seconds:
                Seconds between successive callback invocations.
                Must be greater than zero.
            callback:
                Zero-argument callable to invoke on each tick.

        Returns:
            Unique job identifier string.

        Raises:
            ValueError: If ``interval_seconds`` is zero or negative.
        """
        if interval_seconds <= 0:
            raise ValueError(
                "interval_seconds must be greater than zero."
            )

        job_id = str(uuid4())
        job = _ScheduledJob(
            job_id=job_id,
            interval_seconds=interval_seconds,
            callback=callback,
        )

        with self._lock:
            self._jobs[job_id] = job

        job.start()
        return job_id

    def cancel(self, job_id: str) -> None:
        """Cancel a scheduled job. No-op if ``job_id`` is unknown.

        Args:
            job_id: Identifier returned by a prior ``schedule`` call.
        """
        with self._lock:
            job = self._jobs.pop(job_id, None)

        if job is not None:
            job.cancel()

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def active_job_count(self) -> int:
        """Return the number of currently active jobs."""
        with self._lock:
            return len(self._jobs)

    def cancel_all(self) -> None:
        """Cancel every active job. Intended for teardown/testing."""
        with self._lock:
            jobs = list(self._jobs.values())
            self._jobs.clear()

        for job in jobs:
            job.cancel()


# Runtime protocol check — ensures Scheduler satisfies IScheduler.
assert isinstance(Scheduler(), IScheduler), (
    "Scheduler does not satisfy the IScheduler Protocol."
)
