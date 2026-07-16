"""
Unit tests for communication.bus.scheduler.Scheduler.
"""

from __future__ import annotations

import time
import threading
import pytest

from communication.bus import Scheduler
from communication.interfaces import IScheduler


class TestSchedulerProtocolCompliance:

    def test_satisfies_ischeduler_protocol(self) -> None:
        assert isinstance(Scheduler(), IScheduler)


class TestSchedulerSchedule:

    def test_schedule_returns_str_job_id(self) -> None:
        s = Scheduler()
        job_id = s.schedule(10.0, lambda: None)
        assert isinstance(job_id, str)
        assert len(job_id) > 0
        s.cancel_all()

    def test_schedule_zero_interval_raises(self) -> None:
        s = Scheduler()
        with pytest.raises(ValueError):
            s.schedule(0.0, lambda: None)

    def test_schedule_negative_interval_raises(self) -> None:
        s = Scheduler()
        with pytest.raises(ValueError):
            s.schedule(-1.0, lambda: None)

    def test_schedule_callback_fires(self) -> None:
        s = Scheduler()
        event = threading.Event()
        s.schedule(0.05, event.set)
        fired = event.wait(timeout=1.0)
        s.cancel_all()
        assert fired is True

    def test_schedule_callback_fires_multiple_times(self) -> None:
        s = Scheduler()
        counter: list[int] = []
        lock = threading.Lock()

        def increment() -> None:
            with lock:
                counter.append(1)

        s.schedule(0.05, increment)
        time.sleep(0.25)
        s.cancel_all()
        assert len(counter) >= 2

    def test_multiple_jobs_are_independent(self) -> None:
        s = Scheduler()
        fired_a = threading.Event()
        fired_b = threading.Event()
        s.schedule(0.05, fired_a.set)
        s.schedule(0.05, fired_b.set)
        assert fired_a.wait(timeout=1.0)
        assert fired_b.wait(timeout=1.0)
        s.cancel_all()

    def test_active_job_count_increments(self) -> None:
        s = Scheduler()
        assert s.active_job_count == 0
        s.schedule(10.0, lambda: None)
        s.schedule(10.0, lambda: None)
        assert s.active_job_count == 2
        s.cancel_all()

    def test_unique_job_ids(self) -> None:
        s = Scheduler()
        ids = {s.schedule(10.0, lambda: None) for _ in range(5)}
        assert len(ids) == 5
        s.cancel_all()


class TestSchedulerCancel:

    def test_cancel_stops_callback(self) -> None:
        s = Scheduler()
        counter: list[int] = []
        lock = threading.Lock()

        def increment() -> None:
            with lock:
                counter.append(1)

        job_id = s.schedule(0.05, increment)
        time.sleep(0.12)
        s.cancel(job_id)
        count_at_cancel = len(counter)
        time.sleep(0.15)
        assert len(counter) == count_at_cancel

    def test_cancel_unknown_job_id_is_noop(self) -> None:
        s = Scheduler()
        s.cancel("nonexistent-job-id")  # must not raise

    def test_cancel_decrements_active_count(self) -> None:
        s = Scheduler()
        job_id = s.schedule(10.0, lambda: None)
        assert s.active_job_count == 1
        s.cancel(job_id)
        assert s.active_job_count == 0

    def test_cancel_all_stops_all_jobs(self) -> None:
        s = Scheduler()
        s.schedule(10.0, lambda: None)
        s.schedule(10.0, lambda: None)
        s.cancel_all()
        assert s.active_job_count == 0

    def test_callback_exception_does_not_kill_scheduler(self) -> None:
        s = Scheduler()
        good_event = threading.Event()

        def bad_callback() -> None:
            raise RuntimeError("boom")

        def good_callback() -> None:
            good_event.set()

        s.schedule(0.05, bad_callback)
        s.schedule(0.05, good_callback)
        fired = good_event.wait(timeout=1.0)
        s.cancel_all()
        assert fired is True
