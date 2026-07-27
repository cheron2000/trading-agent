"""
src/dashboard/web/tests/test_web_dashboard.py
=============================================

Unit tests for the Flask web dashboard routes and the module-level
dashboard_state singleton API.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from dashboard.web import dashboard_state as ds
from dashboard.web.app import create_app


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset singleton state between tests."""
    # Re-import to get a fresh module state isn't straightforward;
    # instead we reset via the public API before each test.
    ds._running = False
    ds._kill_requested = False
    ds._strategy_mode = "SIMPLE-RULE"
    ds._portfolio_value = 0.0
    ds._cash = 0.0
    ds._total_pnl = 0.0
    ds._total_return = 0.0
    ds._win_rate = 0.0
    ds._sharpe_ratio = 0.0
    ds._max_drawdown = 0.0
    ds._total_trades = 0
    ds._cycle = 0
    ds._positions.clear()
    ds._trades.clear()
    ds._decisions.clear()
    ds._warnings.clear()
    ds._news.clear()
    ds._chart_history.clear()
    ds._manual_tick_pending = False
    yield


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Route smoke tests
# ---------------------------------------------------------------------------

def test_index_route(client):
    """Index route returns HTTP 200 with the full dashboard HTML."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"AI Trading OS" in response.data
    assert b"equityChart" in response.data


def test_api_snapshot_route(client):
    """/api/snapshot returns a well-formed JSON snapshot."""
    ds.set_running(True, capital=100_000.0)
    ds.update_portfolio(105_000.0, 50_000.0, [], 5_000.0, 0.05)

    response = client.get("/api/snapshot")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["running"] is True
    assert data["portfolio_value"] == 105_000.0
    assert data["cash"] == 50_000.0


def test_api_state_alias(client):
    """/api/state is an alias for /api/snapshot."""
    ds.set_running(True, capital=100_000.0)
    r1 = client.get("/api/snapshot").get_json()
    r2 = client.get("/api/state").get_json()
    assert r1["running"] == r2["running"]
    assert r1["portfolio_value"] == r2["portfolio_value"]


def test_control_tick_route(client):
    """POST /api/control/tick sets the manual-tick flag."""
    response = client.post("/api/control/tick")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert ds.pop_manual_tick() is True
    # Popping a second time should return False
    assert ds.pop_manual_tick() is False


def test_control_strategy_route(client):
    """POST /api/control/strategy switches the active strategy mode."""
    response = client.post(
        "/api/control/strategy",
        data=json.dumps({"mode": "SIMPLE-RULE"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["strategy_mode"] == "SIMPLE-RULE"
    assert ds.snapshot()["strategy_mode"] == "SIMPLE-RULE"


def test_control_strategy_unknown_mode(client):
    """POST /api/control/strategy returns 400 for unknown modes."""
    response = client.post(
        "/api/control/strategy",
        data=json.dumps({"mode": "UNKNOWN"}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_control_kill_route(client):
    """POST /api/control/kill activates the kill switch."""
    response = client.post("/api/control/kill")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert ds.is_kill_requested() is True


# ---------------------------------------------------------------------------
# Singleton state API tests
# ---------------------------------------------------------------------------

def test_set_running_initialises_capital():
    ds.set_running(True, capital=50_000.0)
    snap = ds.snapshot()
    assert snap["running"] is True
    assert snap["initial_capital"] == 50_000.0
    assert snap["cash"] == 50_000.0


def test_update_portfolio_pushes_all_fields():
    ds.update_portfolio(
        portfolio_value=110_000.0,
        cash=60_000.0,
        positions=[{"symbol": "AAPL", "quantity": 10.0, "entry_price": 150.0}],
        total_pnl=10_000.0,
        total_return=0.1,
        win_rate=0.6,
        sharpe_ratio=1.5,
        max_drawdown=0.02,
        total_trades=5,
        cycle=3,
    )
    snap = ds.snapshot()
    assert snap["portfolio_value"] == 110_000.0
    assert snap["cash"] == 60_000.0
    assert snap["total_pnl"] == 10_000.0
    assert snap["total_return"] == 0.1
    assert snap["win_rate"] == 0.6
    assert snap["cycle"] == 3
    assert len(snap["positions"]) == 1
    assert len(snap["chart_history"]) == 1


def test_push_trade():
    ds.push_trade("12:00:00", "AAPL", "BUY", 10.0, 150.0, None)
    ds.push_trade("12:01:00", "AAPL", "SELL", 10.0, 160.0, 100.0)
    snap = ds.snapshot()
    assert len(snap["trades"]) == 2
    # Most recent is first
    assert snap["trades"][0]["action"] == "SELL"
    assert snap["trades"][0]["pnl"] == 100.0


def test_push_decision_dedupes_by_symbol():
    ds.push_decision("AAPL", "BUY", 0.8, "momentum")
    ds.push_decision("AAPL", "SELL", 0.9, "reversal")
    snap = ds.snapshot()
    # Only one AAPL entry, the latest one
    aapl_decisions = [d for d in snap["decisions"] if d["symbol"] == "AAPL"]
    assert len(aapl_decisions) == 1
    assert aapl_decisions[0]["action"] == "SELL"


def test_push_warning():
    ds.push_warning("TSLA", "yfinance timeout")
    snap = ds.snapshot()
    assert len(snap["warnings"]) == 1
    assert snap["warnings"][0]["source"] == "TSLA"
    assert "timeout" in snap["warnings"][0]["message"]


def test_kill_switch_sets_running_false():
    ds.set_running(True, capital=100_000.0)
    assert ds.snapshot()["running"] is True
    ds.request_kill()
    snap = ds.snapshot()
    assert snap["kill_requested"] is True
    assert snap["running"] is False


def test_pop_manual_tick_clears_flag():
    assert ds.pop_manual_tick() is False
    ds.request_manual_tick()
    assert ds.pop_manual_tick() is True
    assert ds.pop_manual_tick() is False
