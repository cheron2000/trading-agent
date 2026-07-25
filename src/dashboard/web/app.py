"""
dashboard.web.app
=================

Flask application factory and API endpoints for the AI Trading OS.

Provides:
  - Live glassmorphic web UI
  - Real-time Server-Sent Events (SSE) streaming
  - Interactive REST APIs for manual ticks, strategy selection, and kill switch

Python Version: 3.11+
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from flask import Flask, Response, render_template, jsonify, request

from dashboard.web.dashboard_state import (
    snapshot,
    new_sse_client,
    remove_sse_client,
    request_manual_tick,
    set_strategy_mode,
    request_kill,
)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def create_app() -> Flask:
    """Create and configure the Flask web application."""
    app = Flask(
        __name__,
        template_folder=str(_TEMPLATE_DIR),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.config["SECRET_KEY"] = "atlas-ai-trading-os-secret"

    @app.route("/")
    def index():
        """Render the command dashboard frontend."""
        return render_template("index.html")

    @app.route("/api/snapshot")
    def api_snapshot():
        """Return the current thread-safe dashboard snapshot."""
        return jsonify(snapshot())

    @app.route("/stream")
    def stream():
        """Server-Sent Events endpoint — streams real-time updates to browser clients."""
        q = new_sse_client()
        initial_payload = json.dumps({"type": "snapshot", "data": snapshot()})

        def generate():
            try:
                # Push immediate initial snapshot
                yield f"data: {initial_payload}\n\n"

                while True:
                    if q:
                        payload = q.popleft()
                        yield f"data: {payload}\n\n"
                    else:
                        time.sleep(0.15)
                        yield ": heartbeat\n\n"
            except GeneratorExit:
                pass
            finally:
                remove_sse_client(q)

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Interactive Control APIs ────────────────────────────────────────────────

    @app.route("/api/control/tick", methods=["POST"])
    def control_tick():
        """Trigger an immediate manual cycle evaluation."""
        request_manual_tick()
        return jsonify({"status": "success", "message": "Manual tick requested"})

    @app.route("/api/control/strategy", methods=["POST"])
    def control_strategy():
        """Switch active strategy mode (GROQ-LLM vs SIMPLE-RULE)."""
        data = request.get_json(silent=True) or {}
        mode = data.get("mode", "GROQ-LLM")
        set_strategy_mode(mode)
        return jsonify({"status": "success", "strategy_mode": mode})

    @app.route("/api/control/kill", methods=["POST"])
    def control_kill():
        """Trigger emergency kill switch to halt trading loop."""
        request_kill()
        return jsonify({"status": "success", "message": "Emergency Kill Switch activated"})

    return app
