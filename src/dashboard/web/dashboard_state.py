"""
dashboard.web.dashboard_state
================================

Thread-safe shared state for the Flask dashboard.

Holds the last N events, trades, decisions, warnings, and metrics
so the Flask SSE endpoint can stream them to the browser.

This module is intentionally free of Flask imports — it is imported
by both run_hour.py (the trading loop) and dashboard_app.py (the
Flask server) to share state across threads via a simple Lock.

Python Version: 3.11+
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

# ── Configuration ───────────────────────────────────────────────────────────
MAX_TRADES      = 100   # recent fills kept in memory
MAX_DECISIONS   = 200   # recent AI decisions (all symbols)
MAX_WARNINGS    = 200   # failures / warnings from any component
MAX_SSE_QUEUE   = 500   # pending SSE events per connected client

_lock = threading.Lock()

# ── Core state ──────────────────────────────────────────────────────────────
_state: dict[str, Any] = {
    # Portfolio snapshot
    "portfolio_value": 0.0,
    "initial_capital": 100_000.0,
    "cash":            0.0,
    "positions":       [],   # list of {symbol, quantity, entry_price}

    # Metrics
    "total_pnl":    0.0,
    "total_return": 0.0,
    "win_rate":     0.0,
    "sharpe_ratio": 0.0,
    "max_drawdown": 0.0,
    "total_trades": 0,

    # Session
    "running":       False,
    "cycle":         0,
    "started_at":    None,
    "symbols":       [],
    "strategy_mode": "GROQ-LLM",

    # Control flags for interactive commands
    "manual_tick_requested": False,
    "kill_requested":        False,

    # News context (last seen per symbol)
    "news": {},    # {symbol: str}
}

# ── Circular buffers ────────────────────────────────────────────────────────
_trades:        deque[dict] = deque(maxlen=MAX_TRADES)
_decisions:     deque[dict] = deque(maxlen=MAX_DECISIONS)
_warnings:      deque[dict] = deque(maxlen=MAX_WARNINGS)
_chart_history: deque[dict] = deque(maxlen=300)

# ── SSE subscriber queues ────────────────────────────────────────────────────
# Each connected browser client gets its own queue.
_sse_queues: list[deque] = []
_sse_lock = threading.Lock()

_SERVER_URL = "http://localhost:5000"


def _post_to_server(action: str, payload: dict) -> None:
    """Safely post state update to running Flask server process if executing in a separate process."""
    def _worker():
        import urllib.request
        import json
        try:
            req = urllib.request.Request(
                f"{_SERVER_URL}/api/internal/update",
                data=json.dumps({"action": action, "payload": payload}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=1.0):
                pass
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


# ── Public write API (called from trading loop / event handlers) ─────────────

def set_running(running: bool, capital: float = 100_000.0,
                symbols: list[str] | None = None,
                _remote_sync: bool = True) -> None:
    with _lock:
        _state["running"]         = running
        _state["initial_capital"] = capital
        _state["symbols"]         = symbols or []
        if running:
            _state["started_at"] = time.time()
            _state["kill_requested"] = False
    if _remote_sync:
        _post_to_server("set_running", {"running": running, "capital": capital, "symbols": symbols})


def update_portfolio(portfolio_value: float, cash: float,
                     positions: list[dict],
                     realized_pnl: float, total_return_pct: float,
                     _remote_sync: bool = True) -> None:
    with _lock:
        _state["portfolio_value"] = portfolio_value
        _state["cash"]            = cash
        _state["positions"]       = list(positions)
        _state["total_pnl"]       = realized_pnl
        _state["total_return"]    = total_return_pct
    if _remote_sync:
        _post_to_server("update_portfolio", {
            "portfolio_value": portfolio_value,
            "cash": cash,
            "positions": list(positions),
            "realized_pnl": realized_pnl,
            "total_return_pct": total_return_pct,
        })


def update_metrics(total_trades: int, total_pnl: float, total_return: float,
                   win_rate: float, sharpe_ratio: float,
                   max_drawdown: float,
                   _remote_sync: bool = True) -> None:
    with _lock:
        _state["total_trades"]  = total_trades
        _state["total_pnl"]     = total_pnl
        _state["total_return"]  = total_return
        _state["win_rate"]      = win_rate
        _state["sharpe_ratio"]  = sharpe_ratio
        _state["max_drawdown"]  = max_drawdown
    if _remote_sync:
        _post_to_server("update_metrics", {
            "total_trades": total_trades,
            "total_pnl": total_pnl,
            "total_return": total_return,
            "win_rate": win_rate,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
        })


def record_chart_point(cycle: int, portfolio_value: float, pnl: float,
                       _remote_sync: bool = True) -> None:
    """Record a historical time series data point for real-time charting."""
    point = {
        "ts": time.strftime("%H:%M:%S"),
        "cycle": cycle,
        "portfolio_value": portfolio_value,
        "pnl": pnl,
    }
    with _lock:
        _chart_history.append(point)
    _push_sse("chart_point", point)
    if _remote_sync:
        _post_to_server("record_chart_point", {"cycle": cycle, "portfolio_value": portfolio_value, "pnl": pnl})


def set_cycle(cycle: int, _remote_sync: bool = True) -> None:
    with _lock:
        _state["cycle"] = cycle
    if _remote_sync:
        _post_to_server("set_cycle", {"cycle": cycle})


def set_strategy_mode(mode: str, _remote_sync: bool = True) -> None:
    """Update active strategy mode (e.g. 'GROQ-LLM' or 'SIMPLE-RULE')."""
    with _lock:
        _state["strategy_mode"] = mode
    _push_sse("strategy_mode", {"mode": mode})


def request_manual_tick() -> None:
    """Flag a request to run an immediate manual tick evaluation."""
    with _lock:
        _state["manual_tick_requested"] = True
    add_warning("CONTROL", "Manual cycle evaluation triggered from Dashboard")


def pop_manual_tick() -> bool:
    """Check and consume a manual tick trigger request."""
    with _lock:
        req = _state["manual_tick_requested"]
        _state["manual_tick_requested"] = False
        if req:
            return True
    try:
        import urllib.request, json
        with urllib.request.urlopen(f"{_SERVER_URL}/api/snapshot", timeout=0.5) as r:
            data = json.loads(r.read().decode("utf-8"))
            if data.get("manual_tick_requested"):
                return True
    except Exception:
        pass
    return False


def request_kill() -> None:
    """Trigger emergency stop command for trading loop."""
    with _lock:
        _state["running"] = False
        _state["kill_requested"] = True
    add_warning("CONTROL", "Emergency Kill Switch activated from Dashboard")


def is_kill_requested() -> bool:
    with _lock:
        if _state["kill_requested"]:
            return True
    try:
        import urllib.request, json
        with urllib.request.urlopen(f"{_SERVER_URL}/api/snapshot", timeout=0.5) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data.get("kill_requested", False)
    except Exception:
        return False


def add_trade(fill_dict: dict, _remote_sync: bool = True) -> None:
    """Record a completed fill (BUY or SELL)."""
    with _lock:
        _trades.appendleft(fill_dict)
    _push_sse("trade", fill_dict)
    if _remote_sync:
        _post_to_server("add_trade", fill_dict)


def add_decision(decision_dict: dict, _remote_sync: bool = True) -> None:
    """Record an AI decision."""
    with _lock:
        _decisions.appendleft(decision_dict)
    _push_sse("decision", decision_dict)
    if _remote_sync:
        _post_to_server("add_decision", decision_dict)


def set_news(symbol: str, news_text: str, _remote_sync: bool = True) -> None:
    """Store the latest news context for a symbol."""
    with _lock:
        _state["news"][symbol] = news_text
    _push_sse("news", {"symbol": symbol, "text": news_text})
    if _remote_sync:
        _post_to_server("set_news", {"symbol": symbol, "text": news_text})


def add_warning(source: str, message: str, _remote_sync: bool = True) -> None:
    """Record a failure, warning, or fallback event."""
    entry = {
        "ts": time.strftime("%H:%M:%S"),
        "source": source,
        "message": message,
    }
    with _lock:
        _warnings.appendleft(entry)
    _push_sse("warning", entry)
    if _remote_sync:
        _post_to_server("add_warning", entry)


# ── Public read API (called from Flask) ─────────────────────────────────────

def snapshot() -> dict:
    """Return a full dashboard snapshot (thread-safe copy)."""
    with _lock:
        uptime = None
        if _state["started_at"]:
            uptime = int(time.time() - _state["started_at"])
        return {
            **_state,
            "uptime_seconds": uptime,
            "trades":        list(_trades),
            "decisions":     list(_decisions),
            "warnings":      list(_warnings),
            "chart_history": list(_chart_history),
        }


# ── SSE pub/sub ─────────────────────────────────────────────────────────────

def new_sse_client() -> deque:
    """Register a new SSE client and return its event queue."""
    q: deque = deque(maxlen=MAX_SSE_QUEUE)
    with _sse_lock:
        _sse_queues.append(q)
    return q


def remove_sse_client(q: deque) -> None:
    """Deregister an SSE client queue."""
    with _sse_lock:
        try:
            _sse_queues.remove(q)
        except ValueError:
            pass


def _push_sse(event_type: str, data: dict) -> None:
    """Push an SSE event to all connected clients."""
    import json
    payload = json.dumps({"type": event_type, "data": data})
    with _sse_lock:
        for q in _sse_queues:
            q.append(payload)

