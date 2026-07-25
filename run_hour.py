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
from pathlib import Path

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
run_label = started_at.strftime("live-run-%Y-%m-%d-%H%M")

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
# Suppress stem control-port socket close noise (expected cleanup messages)
logging.getLogger("stem").setLevel(logging.ERROR)

SYMBOLS = ["AAPL", "MSFT", "GOOGL", "TSLA", "BTC-USD"]  # Added crypto for 24/7 market coverage
# EventBus + RateLimiter
_rl = RateLimiter(default_rate=1000.0, default_capacity=2000.0)
_rl.set_limit("data", rate=500.0, capacity=1000.0)
_rl.set_limit("intelligence", rate=200.0, capacity=400.0)
_rl.set_limit("execution", rate=100.0, capacity=200.0)
bus = EventBus(rate_limiter=_rl)

# Task 6.5 — system.shutdown_requested handler
def _on_shutdown_requested(event):
    global shutdown
    print("\n[Telegram /stop] Graceful shutdown requested via bot.")
    shutdown = True
bus.subscribe("system.shutdown_requested", _on_shutdown_requested)

# Optional Flask dashboard state wiring
_dashboard_enabled = "--dashboard" in sys.argv
if _dashboard_enabled:
    try:
        from dashboard.web.dashboard_state import (
            set_running, add_trade, add_decision, set_news,
            add_warning, update_portfolio, update_metrics, set_cycle
        )
        set_running(True, capital=capital, symbols=SYMBOLS)
        print(f"  Dashboard:      ENABLED — open http://localhost:5000")
    except Exception as _de:
        print(f"  WARNING: Dashboard state init failed — {_de}")
        _dashboard_enabled = False

# Task 6.1 — Optional Telegram notifier
_telegram_notifier = None
if "--telegram" in sys.argv:
    from load_keys import load_telegram_keys
    from dashboard.telegram.telegram_notifier import TelegramNotifier
    try:
        _bot_token, _chat_id = load_telegram_keys()
        _telegram_notifier = TelegramNotifier(
            bus=bus,
            bot_token=_bot_token,
            chat_id=_chat_id,
            notify_hold=False,
        )
        print(f"  Telegram:       ENABLED (bot polling starting...)")
    except (FileNotFoundError, ValueError) as exc:
        print(f"  WARNING: Telegram disabled — {exc}")

# Task 6.2 — Optional Alpaca order manager
_use_alpaca = "--alpaca" in sys.argv
if _use_alpaca:
    from load_keys import load_alpaca_keys
    from execution.broker.alpaca_order_manager import AlpacaOrderManager
    try:
        _alpaca_api_key, _alpaca_secret_key = load_alpaca_keys()
        alpaca_order_manager = AlpacaOrderManager(
            bus=bus,
            initial_portfolio_value=capital,
            api_key=_alpaca_api_key,
            secret_key=_alpaca_secret_key,
            live_trading=False,
        )
        print(f"  Execution:      AlpacaOrderManager (Alpaca paper mode)")
    except (FileNotFoundError, ValueError) as exc:
        print(f"  WARNING: Alpaca disabled — {exc}")
        _use_alpaca = False
else:
    print(f"  Execution:      OrderManager (in-memory paper fill)")

# L3 Data
provider = YFinanceProvider(symbols=SYMBOLS, ttl_seconds=55.0, use_tor=True)
engineer = FeatureEngineer(window_size=5)

# L4 Intelligence — LLM (Groq) primary, SimpleRuleStrategy fallback
from intelligence.strategies.rule_based import SimpleRuleStrategy
from intelligence.agent.llm_agent import LLMAgent
from intelligence.agent.prompt_builder import PromptBuilder
from load_keys import load_groq_key

_rule_strategy = SimpleRuleStrategy(threshold=0.3)

use_llm = "--llm" in sys.argv
groq_key, groq_model = load_groq_key()

if groq_key:
    from intelligence.agent.groq_client import GroqClient
    _groq_client = GroqClient(api_key=groq_key, model=groq_model)
    _llm_agent = LLMAgent(
        llm_client=_groq_client,
        prompt_builder=PromptBuilder(),
        strategy_id=f"groq-{groq_model}",
    )
    print(f"  LLM strategy:   Groq {groq_model} (fallback -> SimpleRule if LLM fails)")
    use_llm = True
else:
    _llm_agent = None
    if "--llm" in sys.argv:
        print("  WARNING: --llm flag set but GROQ_API_KEY not found in keys.env")
        print("           Falling back to SimpleRuleStrategy")
    print(f"  Strategy:       SimpleRuleStrategy (threshold=0.3)")


def evaluate_with_fallback(fv, news_context: str = ""):
    """Use LLM if available, fall back to rule strategy on any error."""
    if _llm_agent is not None:
        try:
            return _llm_agent.evaluate(fv, news_context=news_context)
        except Exception as exc:
            _log = logging.getLogger("run_hour")
            _log.warning("LLM failed for %s — using rule fallback: %s", fv.symbol, exc)
    return _rule_strategy.evaluate(fv)

# News sentiment — Finnhub → AV → Yahoo fallback chain
from data.providers.news_aggregator import NewsAggregator
from load_keys import load_av_keys, load_finnhub_key

_av_keys: list[str] = []
_finnhub_key: str | None = None
try:
    _av_keys = load_av_keys()
except Exception:
    pass
try:
    _finnhub_key = load_finnhub_key()
except Exception:
    pass

_news = NewsAggregator(
    finnhub_key=_finnhub_key,
    av_keys=_av_keys if _av_keys else None,
    max_articles=5,
    cache_ttl=300.0,
)
_news_status = _news.status()
print(f"  News sources:   Finnhub={_news_status['finnhub']}  "
      f"AV={_news_status['alphavantage']}  "
      f"Yahoo={_news_status['yahoo']}")

# L5 Execution
portfolio = Portfolio(initial_cash=capital)
price_feed: dict[str, float] = {}
risk_engine = RiskEngine(price_feed=price_feed, max_position_pct=0.10, min_confidence=0.3)
order_manager = OrderManager(price_feed=price_feed, bus=bus)
tracker = PortfolioTracker(portfolio)

# L6 Analytics
metrics = MetricsEngine(initial_capital=capital)
journal_path = Path(__file__).parent / "data_store" / "live" / f"journal-{run_label}.jsonl"
journal = TradeJournal.load_from_file(journal_path)
report_gen = ReportGenerator(metrics, journal)
print(f"Journal persisting to: {journal_path}\n")

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

# Task 6.3 — Start TelegramNotifier before the trading loop
if _telegram_notifier:
    _telegram_notifier.start()

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

    # Rotate AV key each cycle — spreads budget across all keys
    _news.advance_av_key()

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

            # Fetch news context (cached 5min — actual API call only once per cache_ttl)
            news_context = _news.format_for_prompt(symbol)

            # Print news being sent to AI
            if news_context:
                print(f"  [NEWS] {symbol} news -> AI:")
                for line in news_context.split("\n"):
                    print(f"     {line}")
                if _dashboard_enabled:
                    set_news(symbol, news_context)

            decision = evaluate_with_fallback(fv, news_context=news_context)

            # Print AI response
            print(f"  [AI] {symbol}: {decision.action} (confidence={decision.confidence:.2f}) | {decision.rationale[:90]}")
            if _dashboard_enabled:
                add_decision({
                    "symbol": decision.symbol,
                    "action": decision.action,
                    "confidence": decision.confidence,
                    "rationale": decision.rationale,
                })
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
                _exec = alpaca_order_manager if _use_alpaca else order_manager
                fill = _exec.execute(sell_order)
                tracker.apply_fill(fill)
                ep = entry_prices.pop(sym, fill.fill_price)
                pnl = (fill.fill_price - ep) * fill.quantity
                metrics.record_fill(fill, entry_price=ep)
                journal.record(fill, decision_event)
                total_sell += 1
                print(f"  SELL {sym:<10} qty={fill.quantity:.4f} @ ${fill.fill_price:.2f}  P&L=${pnl:+.2f}")
                if _dashboard_enabled:
                    add_trade({"ts": now.strftime("%H:%M:%S"), "symbol": sym,
                               "action": "SELL", "quantity": fill.quantity,
                               "fill_price": fill.fill_price, "pnl": pnl})

            elif decision.action == "BUY":
                order = risk_engine.approve(decision_event, portfolio)
                if order is None:
                    continue
                _exec = alpaca_order_manager if _use_alpaca else order_manager
                fill = _exec.execute(order)
                tracker.apply_fill(fill)
                entry_prices[sym] = fill.fill_price
                total_buy += 1
                print(f"  BUY  {sym:<10} qty={fill.quantity:.4f} @ ${fill.fill_price:.2f}")

        except Exception as exc:
            print(f"  [WARN] {symbol}: {exc}")

    # Wait for next cycle (skip wait on last cycle)
    # Task 6.4 — Publish portfolio state for Telegram /status, /positions, /pnl commands
    from communication.events.portfolio_state_event import PortfolioStateEvent
    _pv = tracker.portfolio_value(price_feed)
    _pos_list = []
    for _sym in list(entry_prices.keys()):
        _pos = tracker.get_position(_sym, price_feed.get(_sym, 0.0))
        if _pos is not None:
            _pos_list.append({
                "symbol": _sym,
                "quantity": _pos.quantity,
                "entry_price": getattr(_pos, "avg_entry_price", price_feed.get(_sym, 0.0)),
            })
    _realized_pnl = sum(metrics._trade_pnls) if hasattr(metrics, "_trade_pnls") else 0.0
    _total_ret = ((_pv - capital) / capital) if capital > 0 else 0.0
    bus.publish(PortfolioStateEvent(
        event_type="portfolio.state",
        portfolio_value=_pv,
        cash=float(tracker._portfolio._cash),
        realized_pnl=_realized_pnl,
        total_return_pct=_total_ret,
        positions=tuple(_pos_list),
    ))

    if _dashboard_enabled:
        try:
            from dashboard.web.dashboard_state import (
                update_portfolio as _up, update_metrics as _um,
                record_chart_point as _rcp, set_cycle as _sc, is_kill_requested as _ikr
            )
            _sc(cycle)
            _up(_pv, float(tracker._portfolio._cash), _pos_list, _realized_pnl, _total_ret)
            _rep = report_gen.generate(label="live-dashboard")
            _m = _rep.get("metrics", {})
            _um(
                total_trades=_m.get("total_trades", 0),
                total_pnl=_m.get("total_pnl", 0.0),
                total_return=_m.get("total_return", 0.0),
                win_rate=_m.get("win_rate", 0.0),
                sharpe_ratio=_m.get("sharpe_ratio", 0.0),
                max_drawdown=_m.get("max_drawdown", 0.0),
            )
            _rcp(cycle, _pv, _realized_pnl)
            if _ikr():
                print("  [Dashboard] Emergency Kill Switch activated — stopping trading loop.")
                shutdown = True
        except Exception as _d_err:
            pass

    elapsed_after = (datetime.now(timezone.utc) - started_at).total_seconds()
    if elapsed_after < duration_seconds and not shutdown:
        print(f"  Sleeping {fetch_interval}s...\n")
        time.sleep(fetch_interval)

# --- Final Report ---
ended_at = datetime.now(timezone.utc)
label = run_label
report = report_gen.generate(label=label)
m = report["metrics"]

portfolio_val = tracker.portfolio_value(price_feed)

# Task 6.3 — Publish session end event and stop TelegramNotifier
from foundation.base_event import BaseEvent as _BaseEvent
bus.publish(_BaseEvent(event_type="session.end"))
if _telegram_notifier:
    _telegram_notifier.stop()

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
