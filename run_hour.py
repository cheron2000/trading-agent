"""
1-hour live paper trading run with full web dashboard.

Fetches real prices via yfinance every 60 s, runs the 7-layer pipeline,
streams live state to the browser dashboard at http://127.0.0.1:5000,
and prints a final P&L report at the end.

Usage:
    py -3 run_hour.py                         # 1 hour, $100k capital
    py -3 run_hour.py --capital 50000
    py -3 run_hour.py --minutes 30
    py -3 run_hour.py --strategy GROQ-LLM     # use LLM strategy (needs GROQ key)

Dashboard controls (browser UI at http://127.0.0.1:5000):
    Kill Switch    — immediately stops the trading loop
    Trigger Tick   — forces an immediate cycle without waiting for the timer
    Strategy Swap  — switch between SIMPLE-RULE and GROQ-LLM mid-session
"""
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "src")

# --- Parse args ---
capital = 100_000.0
duration_minutes = 60
fetch_interval = 60  # seconds between price fetches
initial_strategy = "SIMPLE-RULE"

for i, arg in enumerate(sys.argv):
    if arg == "--capital" and i + 1 < len(sys.argv):
        capital = float(sys.argv[i + 1])
    if arg == "--minutes" and i + 1 < len(sys.argv):
        duration_minutes = int(sys.argv[i + 1])
    if arg == "--strategy" and i + 1 < len(sys.argv):
        initial_strategy = sys.argv[i + 1].upper()

duration_seconds = duration_minutes * 60
started_at = datetime.now(timezone.utc)
run_label = started_at.strftime("live-run-%Y-%m-%d-%H%M")

print(f"\n{'='*60}")
print("  AI Trading OS — Live Paper Trading + Web Dashboard")
print(f"{'='*60}")
print(f"  Capital:    ${capital:,.2f}")
print(f"  Duration:   {duration_minutes} minutes")
print(f"  Interval:   {fetch_interval}s between cycles")
print(f"  Strategy:   {initial_strategy}")
print(f"  Started:    {started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
print("  Mode:       PAPER + LIVE DATA")
print(f"{'='*60}\n")

# --- Wire up layers ---
import logging

from analytics.journal.trade_journal import TradeJournal
from analytics.metrics.metrics_engine import MetricsEngine
from analytics.reports.report_generator import ReportGenerator
from communication.bus.event_bus import EventBus
from communication.bus.rate_limiter import RateLimiter
from dashboard.web import dashboard_state as ds
from dashboard.web.app import create_app
from data.events.feature_vector_event import FeatureVectorEvent
from data.features.feature_engineer import FeatureEngineer
from data.providers.yfinance_provider import YFinanceProvider
from execution.engine.order_manager import OrderManager
from execution.engine.portfolio_tracker import PortfolioTracker
from execution.models.order import Order
from execution.models.portfolio import Portfolio
from execution.risk.risk_engine import RiskEngine
from intelligence.events.decision_event import DecisionEvent
from intelligence.strategies.rule_based import SimpleRuleStrategy

logging.basicConfig(level=logging.WARNING)

SYMBOLS = ["BTC-USD",]

# --- EventBus + RateLimiter ---
_rl = RateLimiter(default_rate=1000.0, default_capacity=2000.0)
_rl.set_limit("data", rate=500.0, capacity=1000.0)
_rl.set_limit("intelligence", rate=200.0, capacity=400.0)
_rl.set_limit("execution", rate=100.0, capacity=200.0)
bus = EventBus(rate_limiter=_rl)

# --- L3 Data ---
# Try fixture provider first (instant, no network) then fall back to live yfinance
from data.providers.market_provider import MarketDataProvider
try:
    provider = MarketDataProvider()  # Loads from data_store/fixtures/market_ticks.json
    print(f"[OK] Using fixture data provider (instant)\n")
except FileNotFoundError:
    print(f"[WARN] Fixture not found, using live YFinanceProvider...\n")
    provider = YFinanceProvider(symbols=SYMBOLS, ttl_seconds=55.0, use_tor=False)
engineer = FeatureEngineer(window_size=5)

# --- L4 Intelligence ---
strategy = SimpleRuleStrategy(threshold=0.3)

# --- L5 Execution ---
portfolio = Portfolio(initial_cash=capital)
price_feed: dict[str, float] = {}
risk_engine = RiskEngine(price_feed=price_feed, max_position_pct=0.10, min_confidence=0.3)
order_manager = OrderManager(price_feed=price_feed, bus=bus)
tracker = PortfolioTracker(portfolio)

# --- L6 Analytics ---
metrics = MetricsEngine(initial_capital=capital)
journal_path = (
    Path(__file__).parent / "data_store" / "live" / f"journal-{run_label}.jsonl"
)
journal = TradeJournal.load_from_file(journal_path)
report_gen = ReportGenerator(metrics, journal)
print(f"Journal persisting to: {journal_path}\n")

entry_prices: dict[str, float] = {}
cycle = 0
total_buy = 0
total_sell = 0

# --- Dashboard state init ---
ds.set_running(True, capital=capital, symbols=SYMBOLS)
ds.set_strategy_mode(initial_strategy)

# Subscribe bus events → dashboard (for raw event feed)
for _pattern in ("data.feature_vector", "intelligence.decision", "execution.fill"):
    bus.subscribe(_pattern, lambda e: ds.push_decision(
        symbol=getattr(e, "symbol", ""),
        action=getattr(e, "action", ""),
        confidence=getattr(e, "confidence", 0.0),
        rationale=getattr(e, "rationale", ""),
    ) if e.event_type.startswith("intelligence.decision") else None)

# --- Graceful shutdown (Ctrl+C or dashboard kill switch) ---
shutdown = False

def _handle_signal(sig, frame):
    global shutdown
    print("\n\n[!] Interrupted — generating final report...\n")
    shutdown = True

signal.signal(signal.SIGINT, _handle_signal)

# --- Start web dashboard server ---
_dash_app = create_app()
_dash_thread = threading.Thread(
    target=lambda: _dash_app.run(
        host="127.0.0.1", port=5000, debug=False, use_reloader=False
    ),
    daemon=True,
)
_dash_thread.start()
print("Dashboard running at: http://127.0.0.1:5000\n")

# --- Warm price cache ---
print("Warming cache (first batch fetch)...")
provider.warm_cache()
print("Cache warmed. Starting trading loop.\n")


def _push_dashboard_state(cycle_num: int) -> None:
    """Push the full portfolio + metrics snapshot to the dashboard."""
    m = metrics.compute()
    pv = tracker.portfolio_value(price_feed)
    cash = tracker.cash

    # Build positions list for the frontend
    raw_positions = portfolio.all_positions()
    positions_list = [
        {
            "symbol": sym,
            "quantity": qty,
            "entry_price": avg,
        }
        for sym, (qty, avg) in raw_positions.items()
        if qty > 1e-9
    ]

    ds.update_portfolio(
        portfolio_value=pv,
        cash=cash,
        positions=positions_list,
        total_pnl=m.total_pnl,
        total_return=m.total_return,
        win_rate=m.win_rate,
        sharpe_ratio=m.sharpe_ratio,
        max_drawdown=m.max_drawdown,
        total_trades=m.total_trades,
        cycle=cycle_num,
    )


# --- Main trading loop ---
while not shutdown:
    # Check dashboard kill switch
    if ds.is_kill_requested():
        print("\n[!] Kill switch activated from dashboard — stopping.\n")
        shutdown = True
        break

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    if elapsed >= duration_seconds:
        break

    cycle += 1
    remaining = duration_seconds - elapsed
    now = datetime.now(timezone.utc)
    print(
        f"[Cycle {cycle:>3}] {now.strftime('%H:%M:%S')} "
        f"— {int(remaining // 60)}m {int(remaining % 60)}s remaining  "
        f"| strategy={ds.get_strategy_mode()}"
    )

    for symbol in SYMBOLS:
        try:
            tick = provider.fetch(symbol)
            price_feed[symbol] = tick.price

            ticks = provider.fetch_recent(symbol, n=5)
            fv = engineer.compute(ticks)
            fv_event = FeatureVectorEvent(
                event_type="data.feature_vector",
                symbol=fv.symbol,
                timestamp=fv.timestamp,
                features=dict(fv.features),
                source_quality=fv.source_quality,
            )
            bus.publish(fv_event)

            decision = strategy.evaluate(fv)
            sym = symbol.upper()
            has_pos = sym in entry_prices

            if decision.action == "SELL" and not has_pos:
                continue
            if decision.action == "BUY" and has_pos:
                continue
            if decision.action == "HOLD":
                # Still push HOLD to dashboard so rationale is visible
                ds.push_decision(sym, "HOLD", decision.confidence, decision.rationale)
                continue

            decision_event = DecisionEvent(
                event_type="intelligence.decision",
                symbol=decision.symbol,
                action=decision.action,
                confidence=decision.confidence,
                rationale=decision.rationale,
                strategy_id=decision.strategy_id,
            )
            bus.publish(decision_event)
            ds.push_decision(sym, decision.action, decision.confidence, decision.rationale)

            if decision.action == "SELL":
                pos = tracker.get_position(sym, price_feed.get(sym, tick.price))
                if pos is None or pos.quantity < 0.01:
                    continue
                sell_order = Order(
                    symbol=sym,
                    action="SELL",
                    quantity=round(pos.quantity, 6),
                    order_type="MARKET",
                    strategy_id=decision.strategy_id,
                )
                fill = order_manager.execute(sell_order)
                tracker.apply_fill(fill)
                bus.publish(fill)
                ep = entry_prices.pop(sym, fill.fill_price)
                pnl = (fill.fill_price - ep) * fill.quantity
                metrics.record_fill(fill, entry_price=ep)
                journal.record(fill, decision_event)
                total_sell += 1
                ts_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
                ds.push_trade(ts_str, sym, "SELL", fill.quantity, fill.fill_price, pnl)
                print(
                    f"  SELL {sym:<10} qty={fill.quantity:.4f} "
                    f"@ ${fill.fill_price:.2f}  P&L=${pnl:+.2f}"
                )

            elif decision.action == "BUY":
                order = risk_engine.approve(decision_event, portfolio)
                if order is None:
                    continue
                fill = order_manager.execute(order)
                tracker.apply_fill(fill)
                bus.publish(fill)
                entry_prices[sym] = fill.fill_price
                # FIX: record BUY fills in the journal (was missing before)
                metrics.record_fill(fill, entry_price=fill.fill_price)
                journal.record(fill, decision_event)
                total_buy += 1
                ts_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
                ds.push_trade(ts_str, sym, "BUY", fill.quantity, fill.fill_price, None)
                print(
                    f"  BUY  {sym:<10} qty={fill.quantity:.4f} @ ${fill.fill_price:.2f}"
                )

        except Exception as exc:
            msg = f"{symbol}: {exc}"
            print(f"  [WARN] {msg}")
            ds.push_warning(symbol, str(exc))

    # Push full state to dashboard after each cycle
    _push_dashboard_state(cycle)

    # --- Wait for next cycle (respects kill switch + manual tick) ---
    elapsed_after = (datetime.now(timezone.utc) - started_at).total_seconds()
    if elapsed_after < duration_seconds and not shutdown and not ds.is_kill_requested():
        print(f"  Sleeping {fetch_interval}s...\n")
        waited = 0
        while waited < fetch_interval:
            if shutdown or ds.is_kill_requested():
                break
            if ds.pop_manual_tick():
                print("  [Dashboard] Manual tick triggered — skipping sleep.\n")
                break
            time.sleep(1)
            waited += 1


# --- Teardown ---
ds.set_stopped()

# --- Final Report ---
ended_at = datetime.now(timezone.utc)
report = report_gen.generate(label=run_label)
m_dict = report["metrics"]
portfolio_val = tracker.portfolio_value(price_feed)

print(f"\n{'='*60}")
print(f"  FINAL REPORT — {run_label}")
print(f"{'='*60}")
print(f"  Started:          {started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
print(f"  Ended:            {ended_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
print(
    f"  Duration:         "
    f"{int((ended_at - started_at).total_seconds() // 60)}m "
    f"{int((ended_at - started_at).total_seconds() % 60)}s"
)
print(f"  Cycles run:       {cycle}")
print()
print(f"  Initial capital:  ${capital:>12,.2f}")
print(f"  Portfolio value:  ${portfolio_val:>12,.2f}")
print(f"  Total P&L:        ${m_dict['total_pnl']:>+12,.2f}")
print(f"  Total return:     {m_dict['total_return'] * 100:>+.4f}%")
print()
print(f"  BUY  orders:      {total_buy}")
print(f"  SELL orders:      {total_sell}")
print(f"  Round trips:      {m_dict['total_trades']}")
print(f"  Win rate:         {m_dict['win_rate'] * 100:.1f}%")
print(f"  Sharpe ratio:     {m_dict['sharpe_ratio']:.4f}")
print(f"  Max drawdown:     {m_dict['max_drawdown'] * 100:.4f}%")
print()
print(f"  Journal entries:  {report['total_journal_entries']}")
print(f"  Journal integrity:{report['journal_integrity']}")
print(f"{'='*60}\n")
print("Dashboard is still running at http://127.0.0.1:5000 — press Ctrl+C to exit.")

# Keep the dashboard server alive after the run ends so you can review results
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
