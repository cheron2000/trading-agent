"""
src/dashboard/web/tests/test_web_dashboard.py
==============================================

Unit tests for the Flask Web Dashboard and Control APIs.
"""

import json
import pytest
from dashboard.web.app import create_app
from dashboard.web import dashboard_state


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_index_route(client):
    """Verify that index route returns HTTP 200 and loads HTML template."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"AI Trading OS" in response.data
    assert b"equityChart" in response.data


def test_api_snapshot_route(client):
    """Verify that /api/snapshot returns JSON snapshot."""
    dashboard_state.set_running(True, capital=100000.0, symbols=["AAPL"])
    dashboard_state.update_portfolio(105000.0, 50000.0, [], 5000.0, 0.05)
    
    response = client.get("/api/snapshot")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["running"] is True
    assert data["portfolio_value"] == 105000.0
    assert data["cash"] == 50000.0


def test_control_tick_route(client):
    """Verify manual tick trigger endpoint."""
    response = client.post("/api/control/tick")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert dashboard_state.pop_manual_tick() is True


def test_control_strategy_route(client):
    """Verify strategy switching endpoint."""
    response = client.post(
        "/api/control/strategy",
        data=json.dumps({"mode": "SIMPLE-RULE"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["strategy_mode"] == "SIMPLE-RULE"
    assert dashboard_state.snapshot()["strategy_mode"] == "SIMPLE-RULE"


def test_control_kill_route(client):
    """Verify emergency kill switch endpoint."""
    response = client.post("/api/control/kill")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert dashboard_state.is_kill_requested() is True
