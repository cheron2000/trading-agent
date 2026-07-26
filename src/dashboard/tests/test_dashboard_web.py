"""
Tests for dashboard.web.dashboard_state.DashboardState and
dashboard.web.app.create_app.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from dashboard.web.app import create_app
from dashboard.web.dashboard_state import DashboardState

# Local fake events — deliberately NOT imported from intelligence/execution/
# data, since the Dashboard layer must have zero import-time coupling to
# other layers (architecture_lint.py enforces this). DashboardState only
# ever duck-types via getattr()/to_dict(), so these fakes are sufficient.


@dataclass(frozen=True)
class _FakeEvent:
    event_type: str
    symbol: str | None = None
    action: str | None = None
    confidence: float | None = None
    quantity: float | None = None
    fill_price: float | None = None
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
        }


def _decision(symbol="AAPL", action="BUY", confidence=0.8) -> _FakeEvent:
    return _FakeEvent(
        event_type="intelligence.decision",
        symbol=symbol,
        action=action,
        confidence=confidence,
    )


def _fill(symbol="AAPL", action="BUY", quantity=10.0, fill_price=150.0) -> _FakeEvent:
    return _FakeEvent(
        event_type="execution.fill",
        symbol=symbol,
        action=action,
        quantity=quantity,
        fill_price=fill_price,
    )


def _feature_vector_event(symbol="AAPL") -> _FakeEvent:
    return _FakeEvent(event_type="data.feature_vector", symbol=symbol)


class TestDashboardStateEvents:
    def test_empty_snapshot_shape(self) -> None:
        state = DashboardState()
        snap = state.snapshot()
        assert snap["cycle"] == 0
        assert snap["last_update"] is None
        assert snap["positions"] == {}
        assert snap["latest_decisions"] == {}
        assert snap["recent_fills"] == []
        assert snap["event_count"] == 0

    def test_decision_event_indexed_by_symbol(self) -> None:
        state = DashboardState()
        state.record_event(_decision(symbol="AAPL", action="BUY", confidence=0.9))
        snap = state.snapshot()
        assert snap["latest_decisions"]["AAPL"]["action"] == "BUY"
        assert snap["latest_decisions"]["AAPL"]["confidence"] == 0.9
        assert snap["event_count"] == 1

    def test_latest_decision_overwrites_previous_for_same_symbol(self) -> None:
        state = DashboardState()
        state.record_event(_decision(symbol="AAPL", action="BUY"))
        state.record_event(_decision(symbol="AAPL", action="SELL"))
        snap = state.snapshot()
        assert snap["latest_decisions"]["AAPL"]["action"] == "SELL"
        assert len(snap["latest_decisions"]) == 1

    def test_fill_event_appended_to_recent_fills(self) -> None:
        state = DashboardState()
        state.record_event(_fill(symbol="MSFT", quantity=5.0, fill_price=300.0))
        snap = state.snapshot()
        assert len(snap["recent_fills"]) == 1
        assert snap["recent_fills"][0]["symbol"] == "MSFT"
        assert snap["recent_fills"][0]["fill_price"] == 300.0

    def test_non_decision_non_fill_event_only_hits_raw_feed(self) -> None:
        state = DashboardState()
        state.record_event(_feature_vector_event(symbol="AAPL"))
        snap = state.snapshot()
        assert snap["event_count"] == 1
        assert snap["latest_decisions"] == {}
        assert snap["recent_fills"] == []

    def test_recent_events_capped_and_most_recent_first(self) -> None:
        state = DashboardState()
        for i in range(5):
            state.record_event(_decision(symbol=f"S{i}"))
        snap = state.snapshot()
        assert snap["recent_events"][0]["event_id"] == snap["latest_decisions"]["S4"]["event_id"]


class TestDashboardStateDirectPush:
    def test_update_metrics(self) -> None:
        state = DashboardState()
        state.update_metrics({"total_pnl": 123.45, "win_rate": 0.5})
        assert state.snapshot()["metrics"]["total_pnl"] == 123.45

    def test_update_positions_converts_tuples_to_dicts(self) -> None:
        state = DashboardState()
        state.update_positions({"AAPL": (10.0, 150.0)})
        positions = state.snapshot()["positions"]
        assert positions["AAPL"] == {"quantity": 10.0, "avg_price": 150.0}

    def test_tick_updates_cycle_and_last_update(self) -> None:
        state = DashboardState()
        state.tick(7)
        snap = state.snapshot()
        assert snap["cycle"] == 7
        assert snap["last_update"] is not None


class TestDashboardWebApp:
    def test_index_serves_html(self) -> None:
        client = create_app(DashboardState()).test_client()
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"AI Trading OS" in resp.data

    def test_api_state_returns_json_snapshot(self) -> None:
        state = DashboardState()
        state.record_event(_decision(symbol="AAPL"))
        client = create_app(state).test_client()
        resp = client.get("/api/state")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["latest_decisions"]["AAPL"]["symbol"] == "AAPL"
