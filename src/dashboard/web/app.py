"""
dashboard.web.app
====================

create_app() — Flask application factory for the web dashboard.

Read-only: exposes one JSON endpoint (state.snapshot()) and one HTML
page that polls it. Zero write-paths into other layers, matching the
same rule the terminal LiveView follows.

Run standalone for local testing:
    python -m dashboard.web.app

In production this is started from run_hour.py in a background
thread, fed by a DashboardState instance the main loop updates.

Python Version: 3.11+
"""

from __future__ import annotations

from flask import Flask, Response, jsonify

from dashboard.web.dashboard_state import DashboardState

_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Trading OS — Live Dashboard</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px; background: #0b0e14; color: #e6e6e6;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  h1 { font-size: 1.4rem; margin: 0 0 4px; }
  .subtitle { color: #8a8f98; font-size: 0.85rem; margin-bottom: 24px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-bottom: 24px; }
  .card { background: #151922; border: 1px solid #232838; border-radius: 10px; padding: 14px 16px; }
  .card .label { color: #8a8f98; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; }
  .card .value { font-size: 1.6rem; font-weight: 600; margin-top: 4px; }
  .value.pos { color: #4ade80; } .value.neg { color: #f87171; }
  .panel { background: #151922; border: 1px solid #232838; border-radius: 10px; padding: 16px; margin-bottom: 20px; }
  .panel h2 { font-size: 0.95rem; margin: 0 0 12px; color: #c7cbd4; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #1e2330; }
  th { color: #8a8f98; font-weight: 500; }
  .buy { color: #4ade80; } .sell { color: #f87171; } .hold { color: #8a8f98; }
  .empty { color: #565c6b; font-style: italic; padding: 8px; }
  .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; background: #4ade80; }
  .status-dot.stale { background: #f87171; }
</style>
</head>
<body>
  <h1><span class="status-dot" id="statusDot"></span>AI Trading OS — Live Dashboard</h1>
  <div class="subtitle" id="subtitle">connecting...</div>

  <div class="grid" id="metricsGrid"></div>

  <div class="panel">
    <h2>Open Positions</h2>
    <table id="positionsTable"><tbody></tbody></table>
    <div class="empty" id="positionsEmpty" style="display:none;">No open positions</div>
  </div>

  <div class="panel">
    <h2>Latest Decisions</h2>
    <table id="decisionsTable"><tbody></tbody></table>
    <div class="empty" id="decisionsEmpty" style="display:none;">No decisions yet</div>
  </div>

  <div class="panel">
    <h2>Recent Fills</h2>
    <table id="fillsTable"><tbody></tbody></table>
    <div class="empty" id="fillsEmpty" style="display:none;">No fills yet</div>
  </div>

<script>
const fmt = (n, d=2) => (n === null || n === undefined) ? "—" : Number(n).toFixed(d);
const actionClass = a => a === "BUY" ? "buy" : a === "SELL" ? "sell" : "hold";

async function refresh() {
  let data;
  try {
    const resp = await fetch("/api/state");
    data = await resp.json();
    document.getElementById("statusDot").classList.remove("stale");
  } catch (e) {
    document.getElementById("statusDot").classList.add("stale");
    document.getElementById("subtitle").textContent = "connection lost — retrying...";
    return;
  }

  const m = data.metrics || {};
  document.getElementById("subtitle").textContent =
    `cycle ${data.cycle} · last update ${data.last_update ? new Date(data.last_update).toLocaleTimeString() : "—"} · ${data.event_count} events`;

  const equity = m.equity;
  const equityClass = (equity !== undefined && m.initial_capital !== undefined)
    ? (equity >= m.initial_capital ? "pos" : "neg") : "";

  document.getElementById("metricsGrid").innerHTML = `
    <div class="card"><div class="label">Equity</div><div class="value ${equityClass}">$${fmt(equity)}</div></div>
    <div class="card"><div class="label">Max Drawdown</div><div class="value">${fmt((m.max_drawdown || 0) * 100)}%</div></div>
    <div class="card"><div class="label">Win Rate</div><div class="value">${fmt((m.win_rate || 0) * 100)}%</div></div>
    <div class="card"><div class="label">Total P&L</div><div class="value ${(m.total_pnl || 0) >= 0 ? 'pos' : 'neg'}">$${fmt(m.total_pnl)}</div></div>
    <div class="card"><div class="label">Sharpe Ratio</div><div class="value">${fmt(m.sharpe_ratio)}</div></div>
    <div class="card"><div class="label">Total Trades</div><div class="value">${m.total_trades ?? "—"}</div></div>
  `;

  const positions = Object.entries(data.positions || {});
  document.getElementById("positionsEmpty").style.display = positions.length ? "none" : "block";
  document.getElementById("positionsTable").querySelector("tbody").innerHTML =
    (positions.length ? `<tr><th>Symbol</th><th>Qty</th><th>Avg Price</th></tr>` : "") +
    positions.map(([sym, p]) => `<tr><td>${sym}</td><td>${fmt(p.quantity)}</td><td>$${fmt(p.avg_price)}</td></tr>`).join("");

  const decisions = Object.entries(data.latest_decisions || {});
  document.getElementById("decisionsEmpty").style.display = decisions.length ? "none" : "block";
  document.getElementById("decisionsTable").querySelector("tbody").innerHTML =
    (decisions.length ? `<tr><th>Symbol</th><th>Action</th><th>Confidence</th></tr>` : "") +
    decisions.map(([sym, d]) => `<tr><td>${sym}</td><td class="${actionClass(d.action)}">${d.action}</td><td>${fmt(d.confidence, 2)}</td></tr>`).join("");

  const fills = data.recent_fills || [];
  document.getElementById("fillsEmpty").style.display = fills.length ? "none" : "block";
  document.getElementById("fillsTable").querySelector("tbody").innerHTML =
    (fills.length ? `<tr><th>Time</th><th>Symbol</th><th>Action</th><th>Qty</th><th>Price</th></tr>` : "") +
    fills.map(f => `<tr><td>${new Date(f.occurred_at).toLocaleTimeString()}</td><td>${f.symbol}</td><td class="${actionClass(f.action)}">${f.action}</td><td>${fmt(f.quantity)}</td><td>$${fmt(f.fill_price)}</td></tr>`).join("");
}

refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""


def create_app(state: DashboardState) -> Flask:
    """Build the Flask app bound to a given DashboardState.

    Args:
        state: The DashboardState instance run_hour.py (or any caller)
               is feeding via record_event()/update_metrics()/etc.

    Returns:
        A configured Flask app, ready for app.run() or a WSGI server.
    """
    app = Flask(__name__)

    @app.get("/")
    def index() -> Response:
        return Response(_INDEX_HTML, mimetype="text/html")

    @app.get("/api/state")
    def api_state():
        return jsonify(state.snapshot())

    return app


if __name__ == "__main__":
    # Standalone smoke-test run with an empty state.
    create_app(DashboardState()).run(host="127.0.0.1", port=5000, debug=False)
