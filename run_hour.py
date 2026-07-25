"""
1-hour live paper trading run.

Fetches real prices every 60s via Tor, runs the full 7-layer pipeline,
and prints a complete P&L report at the end.

Usage:
    py -3 run_hour.py              # 1 hour, $100k capital
    py -3 run_hour.py --capital 50000
    py -3 run_hour.py --minutes 30
"""
import sys
import time
import signal
from datetime import datetime, timezone

sys.path.insert(0, "src")

# --- Parse args ---
capital = 100_000.0
duration_minutes = 60
fetch_interval = 60  # seconds between price fetches

for i, arg in enumerate(sys.argv):
    if arg == "--capital" and i + 1 < len(sys.argv):
        capital = float(sys.argv[i + 1])
    if arg == "--minutes" and i + 1 < len(sys.argv):
        duration_minutes = int(sys.argv[i + 1])

duration_seconds = duration_minutes * 60
started_at = datetime.now(timezone.utc)

print(f"\n{'='*60}")
print(f"  AI Trading OS — Live 1-Hour Paper Trading Run")
print(f"{'='*60}")
print(f"  Capital:    ${capital:,.2f}")
print(f"  Duration:   {duration_minutes} minutes")
print(f"  Interval:   {fetch_interval}s between cycles")
print(f"  Started:    {started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
print(f"  Mode:       LIVE + TOR")
print(f"{'='*60}\n")

# --- Wire up the pipeline (same as runner.py but we control the loop) ---
from communication.bus.event_bus import EventBus
from communication.bus.rate_limiter import RateLimiter
from data.features.feature_engineer import FeatureEngineer
from data.providers.yfinance_provider import YFinanceProvider
from intelligence.events.decision_event import DecisionEvent
from intelligence.strategies.rule_based import SimpleRuleStrategy
from execution.engine.order_manager import OrderManager
from execution.engine.portfolio_tracker import PortfolioTracker
from execution.models.portfolio import Portfolio
from execution.models.order import Order
from execution.risk.risk_engine import RiskEngine
from analytics.journal.trade_journal import TradeJournal
from analytics.metrics.metrics_engine import MetricsEngine
from analytics.reports.report_generator import ReportGenerator
from data.events.feature_vector_event import FeatureVectorEvent
import logging

logging.basicConfig(level=logging.WARNING)

SYMBOLS = ["AAPL", "MSFT", "GOOGL", "BTC-USD", "ETH-USD", "TSLA"]

# EventBus + RateLimiter
_rl = RateLimiter(default_rate=1000.0, default_capacity=2000.0)
_rl.set_limit("data", rate=500.0, capacity=1000.0)
_rl.set_limit("intelligence", rate=200.0, capacity=400.0)
_rl.set_limit("execution", rate=100.0, capacity=200.0)
bus = EventBus(rate_limiter=_rl)

# L3 Data
provider = YFinanceProvider(symbols=SYMBOLS, ttl_seconds=55.0, use_tor=True)
engineer = FeatureEngineer(window_size=1)

# L4 Intelligence
strategy = SimpleRuleStrategy(threshold=0.3)  # lower threshold = more trades

# L5 Execution
portfolio = Portfolio(initial_cash=capital)
price_feed: dict[str, float] = {}
risk_engine = RiskEngine(price_feed=price_feed, max_position_pct=0.10, min_confidence=0.3)
order_manager = OrderManager(price_feed=price_feed, bus=bus)
tracker = PortfolioTracker(portfolio)

# L6 Analytics
metrics = MetricsEngine(initial_capital=capital)
journal = TradeJournal()
report_gen = ReportGenerator(metrics, journal)

entry_prices: dict[str, float] = {}
cycle = 0
total_buy = 0
total_sell = 0

# --- Graceful shutdown on Ctrl+C ---
shutdown = False
def _handle_signal(sig, frame):
    global shutdown
    print("\n\n[!] Interrupted — generating final report...\n")
    shutdown = True
signal.signal(signal.SIGINT, _handle_signal)

# --- Main loop ---
print("Warming cache (first batch fetch)...")
provider.warm_cache()
print("Cache warmed. Starting trading loop.\n")

while not shutdown:
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    if elapsed >= duration_seconds:
        break

    cycle += 1
    remaining = duration_seconds - elapsed
    now = datetime.now(timezone.utc)
    print(f"[Cycle {cycle:>3}] {now.strftime('%H:%M:%S')} — {int(remaining//60)}m {int(remaining%60)}s remaining")

    for symbol in SYMBOLS:
        try:
            tick = provider.fetch(symbol)
            price_feed[symbol] = tick.price

            # Real 5-tick lookback window (no fabricated/synthetic prices).
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
                ep = entry_prices.pop(sym, fill.fill_price)
                pnl = (fill.fill_price - ep) * fill.quantity
                metrics.record_fill(fill, entry_price=ep)
                journal.record(fill, decision_event)
                total_sell += 1
                print(f"  SELL {sym:<10} qty={fill.quantity:.4f} @ ${fill.fill_price:.2f}  P&L=${pnl:+.2f}")

            elif decision.action == "BUY":
                order = risk_engine.approve(decision_event, portfolio)
                if order is None:
                    continue
                fill = order_manager.execute(order)
                tracker.apply_fill(fill)
                entry_prices[sym] = fill.fill_price
                total_buy += 1
                print(f"  BUY  {sym:<10} qty={fill.quantity:.4f} @ ${fill.fill_price:.2f}")

        except Exception as exc:
            print(f"  [WARN] {symbol}: {exc}")

    # Wait for next cycle (skip wait on last cycle)
    elapsed_after = (datetime.now(timezone.utc) - started_at).total_seconds()
    if elapsed_after < duration_seconds and not shutdown:
        print(f"  Sleeping {fetch_interval}s...\n")
        time.sleep(fetch_interval)

# --- Final Report ---
ended_at = datetime.now(timezone.utc)
label = started_at.strftime("live-run-%Y-%m-%d-%H%M")
report = report_gen.generate(label=label)
m = report["metrics"]

portfolio_val = tracker.portfolio_value(price_feed)

print(f"\n{'='*60}")
print(f"  FINAL REPORT — {label}")
print(f"{'='*60}")
print(f"  Started:          {started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
print(f"  Ended:            {ended_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
print(f"  Duration:         {int((ended_at - started_at).total_seconds() // 60)}m {int((ended_at - started_at).total_seconds() % 60)}s")
print(f"  Cycles run:       {cycle}")
print()
print(f"  Initial capital:  ${capital:>12,.2f}")
print(f"  Portfolio value:  ${portfolio_val:>12,.2f}")
print(f"  Total P&L:        ${m['total_pnl']:>+12,.2f}")
print(f"  Total return:     {m['total_return']*100:>+.4f}%")
print()
print(f"  BUY  orders:      {total_buy}")
print(f"  SELL orders:      {total_sell}")
print(f"  Round trips:      {m['total_trades']}")
print(f"  Win rate:         {m['win_rate']*100:.1f}%")
print(f"  Sharpe ratio:     {m['sharpe_ratio']:.4f}")
print(f"  Max drawdown:     {m['max_drawdown']*100:.4f}%")
print()
print(f"  Journal entries:  {report['total_journal_entries']}")
print(f"  Journal integrity:{report['journal_integrity']}")
print(f"{'='*60}\n")
