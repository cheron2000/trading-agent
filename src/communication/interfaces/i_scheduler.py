"""
communication.interfaces.i_scheduler
======================================

Defines the IScheduler Protocol for the Communication Layer.

This interface specifies the contract for scheduling recurring or
delayed callbacks within the system. Implementations may use threads,
asyncio, or an external scheduler backend.

Zero implementation logic lives here.

Python Version: 3.11+
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class IScheduler(Protocol):
    """Protocol defining the Scheduler contract.

    Implementations provide timer-based callback scheduling.
    Callers depend only on this interface, never on a concrete class.
    """

    def schedule(
        self,
        interval_seconds: float,
        callback: Callable[[], None],
    ) -> str:
        """Schedule a recurring callback at the given interval.

        The callback is invoked repeatedly every ``interval_seconds``
        until explicitly cancelled.

        Args:
            interval_seconds:
                Interval between successive invocations, in seconds.
                Must be greater than zero.

            callback:
                Zero-argument callable to invoke on each tick.

        Returns:
            A unique job identifier string that can be passed to
            ``cancel`` to stop the scheduled callback.

        Raises:
            ValueError:
                If ``interval_seconds`` is zero or negative.
        """
        ...

    def cancel(self, job_id: str) -> None:
        """Cancel a previously scheduled callback.

        After this call the callback will not be invoked again.
        Calling ``cancel`` with an unknown or already-cancelled
        ``job_id`` is a no-op.

        Args:
            job_id:
                The identifier returned by a prior ``schedule`` call.
        """
        ...
