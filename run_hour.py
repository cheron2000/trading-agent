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

# Force unbuffered stdout so prints appear immediately in logs
import functools
print = functools.partial(print, flush=True)  # type: ignore

# --- Parse args ---
capital = 200.0
daily_loss_limit_pct = 0.03   # stop trading if daily P&L drops below -3%
trading_halted = False         # circuit breaker flag
duration_minutes = 120
fetch_interval = 60  # seconds between price fetches
initial_strategy = "ATLAS"

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
from communication.events.portfolio_state_event import PortfolioStateEvent
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
from foundation.base_event import BaseEvent
from intelligence.events.decision_event import DecisionEvent
from intelligence.models.decision import Decision
from intelligence.strategies.rule_based import SimpleRuleStrategy

# Import LLMStrategy conditionally for isinstance checks
try:
    from intelligence.strategies.llm_strategy import LLMStrategy
except ImportError:
    LLMStrategy = None  # type: ignore

try:
    from intelligence.strategies.ollama_strategy import OllamaStrategy
except ImportError:
    OllamaStrategy = None  # type: ignore

logging.basicConfig(level=logging.WARNING)
_log = logging.getLogger(__name__)

SYMBOLS = ["AAPL", "MSFT", "GOOGL", "BTC-USD", "ETH-USD", "TSLA"]

# Symbols that only trade during NYSE market hours
_STOCK_SYMBOLS = {"AAPL", "MSFT", "GOOGL", "TSLA"}
_CRYPTO_SYMBOLS = {"BTC-USD", "ETH-USD"}

# Correlation groups — limit simultaneous long positions within each group
_CORRELATION_GROUPS = [
    {"AAPL", "MSFT", "GOOGL", "TSLA"},  # Tech stocks — max 2 long at once
    {"BTC-USD", "ETH-USD"},              # Crypto — max 1 long at once
]
_MAX_CORRELATED_LONGS = {  # Max simultaneous long positions per group
    0: 3,  # Tech: allow max 3 (of 4)
    1: 2,  # Crypto: allow both BTC + ETH
}

def _get_daily_trend(symbol: str) -> str:
    """Fetch daily trend for a symbol using yfinance.
    Returns 'UPTREND', 'DOWNTREND', or 'NEUTRAL'.
    """
    try:
        import yfinance as yf
        import pandas as pd
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='3mo', interval='1d')
        if hist.empty or len(hist) < 50:
            return 'NEUTRAL'
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)
        close_col = [c for c in hist.columns if str(c).lower() == 'close']
        if not close_col:
            return 'NEUTRAL'
        closes = hist[close_col[0]].values.flatten()
        sma_20 = closes[-20:].mean()
        sma_50 = closes[-50:].mean()
        current = closes[-1]
        if current > sma_20 > sma_50:
            return 'UPTREND'
        elif current < sma_20 < sma_50:
            return 'DOWNTREND'
        return 'NEUTRAL'
    except Exception:
        return 'NEUTRAL'

def _volatility_adjusted_size(base_pct: float, atr_pct: float) -> float:
    """Adjust position size based on ATR volatility.
    
    High volatility → smaller position. Low volatility → larger position.
    """
    if atr_pct <= 0:
        return base_pct
    if atr_pct > 0.03:       # > 3% ATR = high vol
        return base_pct * 0.5  # Half size
    elif atr_pct > 0.02:     # 2-3% ATR = medium vol
        return base_pct * 0.75
    elif atr_pct < 0.01:     # < 1% ATR = low vol
        return base_pct * 1.3  # Bigger size
    return base_pct

def _check_correlation_limit(sym: str, entry_prices: dict) -> bool:
    """Return True if opening a new long position in sym is allowed.
    
    Blocks new BUYs when too many correlated assets are already long.
    """
    for group_idx, group in enumerate(_CORRELATION_GROUPS):
        if sym not in group:
            continue
        max_allowed = _MAX_CORRELATED_LONGS.get(group_idx, 2)
        # Count how many symbols in this group are currently held (excluding sym itself)
        current_longs = sum(1 for s in group if s in entry_prices)
        if current_longs >= max_allowed:
            return False  # Already at limit for this correlation group
    return True  # No limit hit

def _is_market_open(symbol: str) -> bool:
    """Return True if this symbol is currently tradeable.
    
    Stocks: NYSE hours only (Mon-Fri 09:30-16:00 ET).
    Crypto: Always tradeable (24/7 market).
    Pre/after market is excluded to avoid low-quality data.
    """
def _is_market_open(symbol: str) -> bool:
    """Always return True for 24/7 simulation and paper testing."""
    return True

# --- EventBus + RateLimiter ---
_rl = RateLimiter(default_rate=1000.0, default_capacity=2000.0)
_rl.set_limit("data", rate=500.0, capacity=1000.0)
_rl.set_limit("intelligence", rate=200.0, capacity=400.0)
_rl.set_limit("execution", rate=100.0, capacity=200.0)
bus = EventBus(rate_limiter=_rl)

# --- Task 6.1: Add --telegram flag ---
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
    except (FileNotFoundError, ValueError) as exc:
        print(f"  WARNING: Telegram disabled — {exc}")

# --- Task 6.2: Add --alpaca flag ---
_use_alpaca = "--alpaca" in sys.argv
alpaca_order_manager = None
if _use_alpaca:
    from load_keys import load_alpaca_keys
    from execution.broker.alpaca_order_manager import AlpacaOrderManager
    _alpaca_api_key, _alpaca_secret_key = load_alpaca_keys()
    alpaca_order_manager = AlpacaOrderManager(
        bus=bus,
        initial_portfolio_value=capital,
        api_key=_alpaca_api_key,
        secret_key=_alpaca_secret_key,
        live_trading=False,
    )
    print(f"  Execution:      AlpacaOrderManager (paper mode)")
else:
    print(f"  Execution:      OrderManager (in-memory paper fill)")

# --- L3 Data ---
# Try live yfinance first, fall back to fixture data if it fails
from data.providers.market_provider import MarketDataProvider
try:
    provider = YFinanceProvider(symbols=SYMBOLS, ttl_seconds=55.0, use_tor=False)
    # Test real fetch — raise Exception if rate-limited or unavailable
    test_tick = provider.fetch(SYMBOLS[0])
    if not test_tick or test_tick.price <= 0:
        raise ValueError("Invalid tick from YFinance")
    print(f"[OK] Using LIVE YFinance data provider (AAPL=${test_tick.price:.2f})\n")
except Exception as exc:
    print(f"[WARN] YFinance unavailable/rate-limited ({exc}), falling back to instant fixture data...\n")
    provider = MarketDataProvider()
engineer = FeatureEngineer(window_size=20)

# --- L3.5 News Aggregator (for LLM context) ---
from data.providers.news_aggregator import NewsAggregator
from load_keys import load_av_keys, load_finnhub_key

av_keys = load_av_keys()
finnhub_key = load_finnhub_key()
news_agg = NewsAggregator(
    finnhub_key=finnhub_key,
    av_keys=av_keys,
    max_articles=3,
    cache_ttl=300.0,
)
print(f"[OK] News aggregator initialized: {news_agg.status()}\n")

# --- L4 Intelligence ---
# Dynamic strategy selection based on --strategy flag
if initial_strategy in ("ATLAS", "ATLAS-LLM"):
    from load_keys import load_groq_keys, load_groq_model, load_ollama_model, load_ollama_host
    from intelligence.strategies.atlas_strategy import AtlasStrategy
    groq_keys = load_groq_keys()
    groq_model = load_groq_model()
    ollama_model = load_ollama_model()
    ollama_host = load_ollama_host()
    strategy = AtlasStrategy(
        groq_api_key=groq_keys,
        groq_model=groq_model,
        ollama_host=ollama_host,
        ollama_model=ollama_model,
    )
    engine_desc = f"Groq ({groq_model})" if groq_keys else f"Local Ollama ({ollama_model})"
    print(f"[OK] ATLAS strategy enabled — Primary engine: {engine_desc}")
elif initial_strategy == "GROQ-LLM":
    from load_keys import load_groq_keys, load_groq_model
    from intelligence.strategies.llm_strategy import LLMStrategy
    groq_keys = load_groq_keys()
    groq_model = load_groq_model()
    if not groq_keys:
        print("[ERROR] GROQ_API_KEY not found in keys.env — falling back to SIMPLE-RULE")
        strategy = SimpleRuleStrategy(threshold=0.3)
    else:
        strategy = LLMStrategy(api_key=groq_keys, model=groq_model)
        print(f"[OK] LLM strategy enabled — model: {groq_model}, keys: {len(groq_keys)}")
elif initial_strategy == "OLLAMA":
    from load_keys import load_ollama_model, load_ollama_host
    ollama_model = load_ollama_model()
    ollama_host = load_ollama_host()
    if OllamaStrategy is None:
        print("[ERROR] OllamaStrategy could not be imported — falling back to SIMPLE-RULE")
        strategy = SimpleRuleStrategy(threshold=0.3)
    else:
        strategy = OllamaStrategy(model=ollama_model, host=ollama_host)
        print(f"[OK] OLLAMA strategy enabled — model: {ollama_model}, host: {ollama_host}")
else:
    strategy = SimpleRuleStrategy(threshold=0.3)

# --- L5 Execution ---
portfolio = Portfolio(initial_cash=capital)
price_feed: dict[str, float] = {}
risk_engine = RiskEngine(price_feed=price_feed, max_position_pct=0.25, min_confidence=0.3, max_total_exposure_pct=0.90)
order_manager = OrderManager(price_feed=price_feed, bus=bus)
tracker = PortfolioTracker(portfolio)

# --- Task 6.6: Unify order execution dispatch ---
_exec = alpaca_order_manager if _use_alpaca else order_manager

# --- L6 Analytics ---
metrics = MetricsEngine(initial_capital=capital)
journal_path = (
    Path(__file__).parent / "data_store" / "live" / f"journal-{run_label}.jsonl"
)
journal = TradeJournal.load_from_file(journal_path)
report_gen = ReportGenerator(metrics, journal)
print(f"Journal persisting to: {journal_path}\n")

entry_prices: dict[str, float] = {}
hold_cycles_tracker: dict[str, int] = {}
trailing_stops: dict[str, float] = {}  # symbol → highest stop price seen
_daily_trend_cache: dict[str, tuple[str, float]] = {}  # sym -> (trend, timestamp)
_news_context_cache: dict[str, str] = {}  # symbol -> latest news context string

# Restore entry prices from existing positions (for restart resilience)
for sym, (qty, avg_price) in portfolio.all_positions().items():
    if qty > 1e-9:  # Has position
        entry_prices[sym] = avg_price

cycle = 0
total_buy = 0
total_sell = 0
daily_start_value = capital    # portfolio value at start of session
# ATR-based dynamic stops (computed per-symbol each cycle from feature vector)
# Fallback constants used if ATR is not available
_DEFAULT_STOP_MULTIPLIER = 2.0   # Stop = entry - 2 * ATR
_DEFAULT_PROFIT_MULTIPLIER = 3.0 # Target = entry + 3 * ATR (1:3 risk/reward)
_FALLBACK_STOP_PCT = -0.015      # Fallback: 1.5% stop if ATR unavailable  
_FALLBACK_PROFIT_PCT = 0.03      # Fallback: 3% profit target if ATR unavailable

# --- Dashboard state init ---
ds.set_running(True, capital=capital, symbols=SYMBOLS)
ds.set_strategy_mode(initial_strategy)

# Subscribe bus events → dashboard (for raw event feed)
# (intelligence.decision subscription removed to avoid duplicate pushes)

# --- Graceful shutdown (Ctrl+C or dashboard kill switch) ---
shutdown = False

def _on_shutdown_requested(event: BaseEvent) -> None:
    """Task 6.5: Handle system.shutdown_requested event."""
    global shutdown
    print("\n[Telegram /stop] Graceful shutdown requested via bot.")
    shutdown = True

bus.subscribe("system.shutdown_requested", _on_shutdown_requested)

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

# --- Task 6.3: Start TelegramNotifier before trading loop ---
if _telegram_notifier:
    _telegram_notifier.start()
    print("Telegram bot started (polling enabled)\n")

# --- Warm price cache ---
print("Warming cache (first batch fetch)...")
provider.warm_cache()


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

    # --- Task 6.4: Publish PortfolioStateEvent ---
    bus.publish(PortfolioStateEvent(
        event_type="portfolio.state",
        portfolio_value=pv,
        cash=cash,
        realized_pnl=m.total_pnl,
        total_return_pct=((pv - capital) / capital) if capital > 0 else 0.0,
        positions=tuple(positions_list),
    ))


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
    
    # Support mid-session strategy swap via dashboard
    current_mode = ds.get_strategy_mode()
    if current_mode == "GROQ-LLM" and not isinstance(strategy, LLMStrategy):
        # User switched to LLM via dashboard
        from load_keys import load_groq_keys, load_groq_model
        from intelligence.strategies.llm_strategy import LLMStrategy
        groq_keys = load_groq_keys()
        groq_model = load_groq_model()
        if groq_keys:
            strategy = LLMStrategy(api_key=groq_keys, model=groq_model)
            print(f"\n[STRATEGY SWAP] Switched to LLM strategy (model: {groq_model}, keys: {len(groq_keys)})\n")
        else:
            print("\n[STRATEGY SWAP] Cannot switch to LLM — GROQ_API_KEY not set\n")
            ds.set_strategy_mode("SIMPLE-RULE")
    elif current_mode == "OLLAMA" and (OllamaStrategy is None or not isinstance(strategy, OllamaStrategy)):
        # User switched to Ollama via dashboard
        from load_keys import load_ollama_model, load_ollama_host
        ollama_model = load_ollama_model()
        ollama_host = load_ollama_host()
        if OllamaStrategy is not None:
            strategy = OllamaStrategy(model=ollama_model, host=ollama_host)
            print(f"\n[STRATEGY SWAP] Switched to OLLAMA strategy (model: {ollama_model})\n")
        else:
            print("\n[STRATEGY SWAP] Cannot switch to OLLAMA — OllamaStrategy not imported\n")
            ds.set_strategy_mode("SIMPLE-RULE")
    elif current_mode == "SIMPLE-RULE" and not isinstance(strategy, SimpleRuleStrategy):
        # User switched to rule-based
        strategy = SimpleRuleStrategy(threshold=0.3)
        print("\n[STRATEGY SWAP] Switched to SimpleRuleStrategy\n")
    
    print(
        f"[Cycle {cycle:>3}] {now.strftime('%H:%M:%S')} "
        f"— {int(remaining // 60)}m {int(remaining % 60)}s remaining  "
        f"| strategy={ds.get_strategy_mode()}"
    )
    closed_stocks = [s for s in _STOCK_SYMBOLS if not _is_market_open(s)]
    if closed_stocks:
        print(f"  [Market Hours] NYSE closed — skipping: {', '.join(sorted(closed_stocks))}")

    # --- Fetch news (non-blocking with timeout) ---
    # News HTTP calls can hang (Tor proxy, rate limits). Use a background
    # thread with a hard 5-second timeout so trading is never blocked.
    import threading as _th

    def _fetch_news_batch():
        news_agg.advance_av_key()
        for _sym in SYMBOLS:
            try:
                _ctx = news_agg.format_for_prompt(_sym)
                if _ctx:
                    _news_context_cache[_sym] = _ctx
                    _lines = _ctx.strip().split('\n')
                    if _lines:
                        ds.push_news(_sym, _lines[0].replace('- ', '').strip())
            except Exception as _e:
                pass  # silently skip — trading is more important

    _news_thread = _th.Thread(target=_fetch_news_batch, daemon=True)
    _news_thread.start()
    _news_thread.join(timeout=5.0)  # hard 5s cap
    if _news_thread.is_alive():
        print("  [NEWS] Timeout — skipping news (trading continues)")

    # --- Circuit breaker: halt trading if daily loss limit hit ---
    if not trading_halted:
        current_value = tracker.portfolio_value(price_feed)
        daily_pnl_pct = (current_value - daily_start_value) / daily_start_value
        if daily_pnl_pct <= -daily_loss_limit_pct:
            trading_halted = True
            msg = f"CIRCUIT BREAKER: Daily loss limit hit ({daily_pnl_pct*100:.2f}%). Trading halted for this session."
            print(f"\n  [!!!] {msg}\n")
            ds.push_warning(msg)

    if trading_halted:
        # Still update dashboard but skip all trading
        try:
            _push_dashboard_state(cycle)
        except Exception:
            pass
        # Wait for next cycle
        time.sleep(fetch_interval)
        continue

    for symbol in SYMBOLS:
        try:
            # Skip stocks outside market hours
            if not _is_market_open(symbol):
                continue
            
            print(f"  [{symbol}] Fetching price...")
            try:
                tick = provider.fetch(symbol)
                if not tick or tick.price <= 0:
                    raise ValueError("No price returned")
            except Exception as _fetch_err:
                if not isinstance(provider, MarketDataProvider):
                    print(f"  [WARN] YFinance rate limited ({_fetch_err}) — switching to fixture provider")
                    provider = MarketDataProvider()
                    tick = provider.fetch(symbol)
                else:
                    continue
            price_feed[symbol] = tick.price
            print(f"  [{symbol}] Price: ${tick.price:.2f}")

            ticks = provider.fetch_recent(symbol, n=26)
            fv = engineer.compute(ticks)
            fv_event = FeatureVectorEvent(
                event_type="data.feature_vector",
                symbol=fv.symbol,
                timestamp=fv.timestamp,
                features=dict(fv.features),
                source_quality=fv.source_quality,
            )
            bus.publish(fv_event)

            sym = symbol.upper()
            if sym in entry_prices:
                hold_cycles_tracker[sym] = hold_cycles_tracker.get(sym, 0) + 1
            
            # Multi-timeframe filter: check daily trend
            import time as _time_mod
            _cached = _daily_trend_cache.get(sym)
            if _cached and (_time_mod.monotonic() - _cached[1]) < 1800:  # 30 min cache
                daily_trend = _cached[0]
            else:
                daily_trend = _get_daily_trend(symbol)
                _daily_trend_cache[sym] = (daily_trend, _time_mod.monotonic())
                print(f"  [{symbol}] Daily trend: {daily_trend}")

            # Build position context for LLM memory
            pos_context = None
            if hasattr(strategy, 'evaluate_with_context'):
                _pos_entry = entry_prices.get(sym)
                _pos_price = tick.price
                pos_context = {
                    "has_position": sym in entry_prices,
                    "entry_price": _pos_entry or 0.0,
                    "current_price": _pos_price,
                    "pnl_pct": ((_pos_price - _pos_entry) / _pos_entry * 100.0)
                               if _pos_entry and _pos_entry > 0 else 0.0,
                    "hold_cycles": hold_cycles_tracker.get(sym, 0),
                    "news_context": _news_context_cache.get(sym, ""),
                }
                print(f"  [{symbol}] Asking {strategy.strategy_id}...")
                decision = strategy.evaluate_with_context(fv, position_context=pos_context)
            else:
                decision = strategy.evaluate(fv)
            print(f"  [{symbol}] Decision: {decision.action} (confidence={decision.confidence:.2f})")
            has_pos = sym in entry_prices

            # Multi-timeframe filter: downgrade signals against daily trend
            if decision.action == 'BUY' and daily_trend == 'DOWNTREND':
                print(f"  [{symbol}] BUY downgraded to HOLD (daily trend is DOWNTREND)")
                decision = Decision(symbol=sym, action='HOLD', confidence=0.4,
                    rationale=f'BUY signal overridden by daily DOWNTREND', strategy_id='trend-filter')
            elif decision.action == 'SELL' and daily_trend == 'UPTREND' and not has_pos:
                print(f"  [{symbol}] SELL downgraded to HOLD (daily trend is UPTREND)")
                decision = Decision(symbol=sym, action='HOLD', confidence=0.4,
                    rationale=f'SELL signal overridden by daily UPTREND', strategy_id='trend-filter')

            current_price = tick.price

            # --- NEW: Check for profit-taking or stop-loss on existing positions ---
            if has_pos and entry_prices[sym] > 0:
                entry = entry_prices[sym]
                atr_val = fv.features.get("atr", 0.0)
                
                # Compute trailing stop
                if atr_val > 0:
                    new_stop = current_price - 2.0 * atr_val
                    target_price = entry + 3.0 * atr_val
                else:
                    new_stop = current_price * (1 - 0.02)  # 2% trailing
                    target_price = entry * (1 + 0.04)       # 4% target
                
                # Ratchet up — trailing stop only goes UP, never down
                prev_stop = trailing_stops.get(sym, 0.0)
                trailing_stops[sym] = max(prev_stop, new_stop)
                actual_stop = trailing_stops[sym]
                
                at_stop = current_price <= actual_stop
                at_target = current_price >= target_price
                
                if at_target:
                    pct_gain = (current_price - entry) / entry * 100
                    decision = Decision(
                        symbol=sym, action="SELL", confidence=0.95,
                        rationale=f"Take profit: +{pct_gain:.2f}% at ${current_price:.2f} (target hit)",
                        strategy_id="profit-target",
                    )
                elif at_stop and current_price < entry:  # Only stop out at a loss
                    pct_loss = (current_price - entry) / entry * 100
                    decision = Decision(
                        symbol=sym, action="SELL", confidence=0.95,
                        rationale=f"Trailing stop: {pct_loss:.2f}% at ${current_price:.2f} (stop=${actual_stop:.2f})",
                        strategy_id="trailing-stop",
                    )

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

            if decision.action == "SELL" and not has_pos:
                continue
            if decision.action == "BUY" and has_pos:
                continue
            if decision.action == "HOLD":
                print(f"  HOLD {sym:<10} (Conf: {decision.confidence:.2f}) - {decision.rationale}")
                continue

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
                fill = _exec.execute(sell_order)
                tracker.apply_fill(fill)
                bus.publish(fill)
                ep = entry_prices.pop(sym, fill.fill_price)
                hold_cycles_tracker.pop(sym, None)
                trailing_stops.pop(sym, None)
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
                atr_pct = fv.features.get('atr', 0.0) / current_price if current_price > 0 else 0
                adjusted_pct = _volatility_adjusted_size(0.25, atr_pct)
                risk_engine._max_position_pct = adjusted_pct
                
                order = risk_engine.approve(decision_event, portfolio)
                if order is None:
                    continue
                
                # Correlation check: block BUY if too many correlated assets held
                if not _check_correlation_limit(sym, entry_prices):
                    _log.info("Correlation limit: skipping BUY for %s (too many correlated longs)", sym)
                    print(f"  [CORRELATION] Skipping BUY {sym} — too many correlated positions")
                    continue
                
                fill = _exec.execute(order)
                tracker.apply_fill(fill)
                bus.publish(fill)
                entry_prices[sym] = fill.fill_price
                hold_cycles_tracker[sym] = 0
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
    try:
        _push_dashboard_state(cycle)
    except Exception as exc:
        ds.push_warning(f"Dashboard state update failed: {exc}")
        print(f"  [WARNING] Dashboard state update failed: {exc}")

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

# --- Final Report (Calculate metrics FIRST before using them) ---
ended_at = datetime.now(timezone.utc)
report = report_gen.generate(label=run_label)
m_dict = report["metrics"]
portfolio_val = tracker.portfolio_value(price_feed)

# --- Task 6.5: Publish session.end event ---
# Note: BaseEvent only supports event_type; detailed metrics are available via report
bus.publish(BaseEvent(event_type="session.end"))

# --- Task 6.3: Stop TelegramNotifier after session end ---
if _telegram_notifier:
    _telegram_notifier.stop()

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
