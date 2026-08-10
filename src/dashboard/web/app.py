"""
dashboard.web.app
====================

Flask application factory for the AI Trading OS web dashboard.

Endpoints:
  GET  /                    → serve the full command dashboard (templates/index.html)
  GET  /api/snapshot        → JSON snapshot for the full dashboard frontend
  GET  /api/state           → JSON snapshot (legacy / unit-test compat, same data)
  GET  /stream              → SSE stream pushing real-time snapshots
  POST /api/control/tick    → manually trigger a trading cycle
  POST /api/control/strategy → switch active strategy mode
  POST /api/control/kill    → emergency kill switch

The module-level `dashboard_state` singleton is the primary data source for
run_hour.py and the control endpoints. The optional `DashboardState` class
instance path (for isolated unit tests) is also supported via create_app(state).

Python Version: 3.11+
"""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from pathlib import Path

from flask import Flask, Response, jsonify, request, stream_with_context

from dashboard.web import dashboard_state as _ds
from dashboard.web.dashboard_state import DashboardState


def create_app(state: DashboardState | None = None) -> Flask:
    """Build and return the configured Flask app.

    Args:
        state: Optional DashboardState instance for isolated testing.
               When None (production), the module-level singleton is used.

    Returns:
        A configured Flask app ready for app.run() or a WSGI server.
    """
    # Locate templates/ relative to this file so Flask finds index.html
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    app = Flask(__name__, template_folder=template_dir)

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------

    @app.get("/")
    def index() -> Response:
        # Serve the full-featured command dashboard
        safe_template_dir = Path(template_dir).resolve()
        safe_path = (safe_template_dir / "index.html").resolve()
        if not str(safe_path).startswith(str(safe_template_dir)):
            return Response("Forbidden", status=403)
        with open(safe_path, encoding="utf-8") as f:
            html = f.read()
        return Response(html, mimetype="text/html")

    # ------------------------------------------------------------------
    # JSON snapshot endpoints (dual path: singleton or injected instance)
    # ------------------------------------------------------------------

    @app.get("/api/snapshot")
    def api_snapshot():
        """Full snapshot for the command dashboard frontend."""
        if state is not None:
            return jsonify(state.snapshot())
        return jsonify(_ds.snapshot())

    @app.get("/api/state")
    def api_state():
        """Legacy alias — same data, keeps old callers working."""
        if state is not None:
            return jsonify(state.snapshot())
        return jsonify(_ds.snapshot())

    # ------------------------------------------------------------------
    # SSE stream
    # ------------------------------------------------------------------

    @app.get("/stream")
    def stream():
        """Server-Sent Events stream pushing snapshot updates to the browser."""

        def _generate() -> Generator[str, None, None]:
            q = _ds.subscribe_sse()
            try:
                # Send an immediate snapshot so the browser doesn't wait
                yield f"data: {json.dumps({'type': 'snapshot', 'data': _ds.snapshot()})}\n\n"
                while True:
                    try:
                        msg = q.get(timeout=25)
                        yield f"data: {msg}\n\n"
                    except Exception:
                        # Heartbeat to keep the connection alive
                        yield 'data: {"type":"heartbeat"}\n\n'
            finally:
                _ds.unsubscribe_sse(q)

        return Response(
            stream_with_context(_generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # ------------------------------------------------------------------
    # Control endpoints
    # ------------------------------------------------------------------

    @app.post("/api/control/tick")
    def control_tick():
        """Request a manual trading cycle on the next loop iteration."""
        _ds.request_manual_tick()
        return jsonify({"status": "success", "message": "Manual tick requested"})

    @app.post("/api/control/strategy")
    def control_strategy():
        """Switch the active strategy mode."""
        body = request.get_json(silent=True) or {}
        mode = body.get("mode", "SIMPLE-RULE")
        if mode not in ("ATLAS", "GROQ-LLM", "SIMPLE-RULE", "OLLAMA"):
            return jsonify({"status": "error", "message": f"Unknown mode: {mode}"}), 400
        _ds.set_strategy_mode(mode)
        return jsonify({"status": "success", "strategy_mode": mode})

    @app.post("/api/control/kill")
    def control_kill():
        """Emergency kill switch — halts the trading loop immediately."""
        _ds.request_kill()
        return jsonify({"status": "success", "message": "Kill switch activated"})

    return app


if __name__ == "__main__":
    # Standalone smoke-test: start with empty singleton state
    create_app().run(host="127.0.0.1", port=5000, debug=False)
