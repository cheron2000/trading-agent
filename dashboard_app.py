"""
dashboard_app.py — Flask Live Command Dashboard for AI Trading OS.

Runs as a standalone web app or alongside run_hour.py.
Shared state is managed asynchronously via dashboard_state.py over the EventBus.

Usage:
    # Terminal 1 — start the dashboard server
    py -3 dashboard_app.py

    # Terminal 2 — start the trading session
    py -3 run_hour.py --dashboard --minutes 390

Open http://localhost:5000 in your browser.
"""

import sys

sys.path.insert(0, "src")

from dashboard.web.app import create_app

app = create_app()

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  AI Trading OS — Live Command Dashboard (Flask)")
    print("=" * 60)
    print("  URL:              http://localhost:5000")
    print("  Start trading:    py -3 run_hour.py --dashboard")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
