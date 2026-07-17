"""
paper_trading.runner
=====================

PaperTradingRunner — wires all 7 layers and runs a fixture-based
paper trading simulation.

Flow per tick:
  DataPipeline.run(symbol) → FeatureVectorEvent
  SimpleRuleStrategy.evaluate(fv) → Decision
  RiskEngine.approve(decision_event, portfolio) → Order | None
  OrderManager.execute(order) → FillEvent
  PortfolioTracker.apply_fill(fill)
  MetricsEngine.record_fill(fill, entry_price)
  TradeJournal.record(fill, decision_event)

Returns ReportGenerator.generate() dict at the end.

Python Version: 3.11+
"""

from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta
from pathlib import Path

from communication.bus.event_bus import EventBus
from data.events.feature_vector_event import FeatureVectorEvent
from data.features.feature_engineer import FeatureEngineer
from data.models.market_tick import MarketTick
from data.normalizers.market_normalizer import MarketNormalizer
from data.pipeline import DataPipeline
from data.providers.i_data_provider import IDataProvider
from data.providers.market_provider import MarketDataProvider
from data.providers.yfinance_provider import YFinanceProvider
from intelligence.events.decision_event import DecisionEvent
from intelligence.strategies.rule_based import SimpleRuleStrategy
from execution.engine.order_manager import OrderManager
from execution.engine.portfolio_tracker import PortfolioTracker
from execution.models.portfolio import Portfolio
from execution.risk.risk_engine import RiskEngine
from analytics.journal.trade_journal import TradeJournal
from analytics.metrics.metrics_engine import MetricsEngine
from analytics.reports.report_generator import ReportGenerator


# Default fixture path
_DEFAULT_FIXTURE = (
    Path(__file__).parents[2] / "data_store" / "fixtures" / "market_ticks.json"
)

# Symbols available in the fixture
_FIXTURE_SYMBOLS = ["AAPL", "MSFT", "GOOGL", "BTC-USD", "ETH-USD", "TSLA"]


class PaperTradingRunner:
    """Runs a paper trading simulation.

    Supports two modes:
      - Fixture mode (default): uses static JSON data, fully offline.
      - Live mode: fetches real delayed prices from Yahoo Finance.

    Usage::

        # Fixture mode (offline, deterministic)
        runner = PaperTradingRunner()
        report = runner.run()

        # Live mode (real delayed prices from Yahoo Finance)
        runner = PaperTradingRunner(live=True)
        report = runner.run()
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        run_days: int = 30,
        threshold: float = 0.5,
        live: bool = False,
        fixture_path: Path | str = _DEFAULT_FIXTURE,
    ) -> None:
        """
        Args:
            initial_capital: Starting cash for the portfolio.
            run_days:        Number of simulated trading days.
            threshold:       SimpleRuleStrategy price_change_pct threshold.
            live:            If True, use YFinanceProvider for real prices.
                             If False (default), use fixture data.
            fixture_path:    Path to fixture JSON (ignored when live=True).

        Raises:
            ValueError: If initial_capital <= 0 or run_days < 1.
        """
        if initial_capital <= 0:
            raise ValueError("initial_capital must be > 0.")
        if run_days < 1:
            raise ValueError("run_days must be >= 1.")

        self._run_days = run_days
        self._live = live

        # ------------------------------------------------------------------
        # Wire up all layers
        # ------------------------------------------------------------------
        self._bus = EventBus()

        # L3 — Data
        if live:
            self._provider: IDataProvider = YFinanceProvider(
                symbols=_FIXTURE_SYMBOLS,
                ttl_seconds=60.0,   # cache prices for 60s — safe for Yahoo
            )
            self._normalizer = MarketNormalizer(source="yfinance")
            # Warm the cache with a single batch request before the loop
            self._provider.warm_cache()  # type: ignore[attr-defined]
        else:
            self._provider = MarketDataProvider(fixture_path=Path(fixture_path))
            self._normalizer = MarketNormalizer(source="fixture")
        self._engineer = FeatureEngineer(window_size=1)
        self._pipeline = DataPipeline(
            provider=self._provider,
            normalizer=self._normalizer,
            engineer=self._engineer,
            bus=self._bus,
        )

        # L4 — Intelligence
        self._strategy = SimpleRuleStrategy(threshold=threshold)

        # L5 — Execution
        self._portfolio = Portfolio(initial_cash=initial_capital)
        # Price feed: pull from the already-warmed cache (live) or fetch from fixture
        import time as _time
        self._price_feed: dict[str, float] = {}
        for sym in _FIXTURE_SYMBOLS:
            try:
                tick = self._provider.fetch(sym)
                self._price_feed[sym] = round(tick.price, 4)
            except Exception:
                self._price_feed[sym] = 1.0  # fallback placeholder
        self._risk_engine = RiskEngine(
            price_feed=self._price_feed,
            max_position_pct=0.05,
            min_confidence=0.3,
        )
        self._order_manager = OrderManager(
            price_feed=self._price_feed,
            bus=self._bus,
        )
        self._portfolio_tracker = PortfolioTracker(self._portfolio)

        # L6 — Analytics
        self._metrics = MetricsEngine(initial_capital=initial_capital)
        self._journal = TradeJournal()
        self._report_gen = ReportGenerator(self._metrics, self._journal)

        # Track entry prices for P&L calculation
        self._entry_prices: dict[str, float] = {}
        self._day_counter: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """Execute the full paper trading simulation.

        Iterates over symbols x run_days, processing each tick through
        the full pipeline.

        Returns:
            ReportGenerator.generate() dict with final metrics.
        """
        label = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for day in range(self._run_days):
            self._day_counter = day
            for symbol in _FIXTURE_SYMBOLS:
                self._process_tick(symbol)
            # In live mode, wait 60s between day cycles to respect rate limits
            if self._live and day < self._run_days - 1:
                import time as _t
                _t.sleep(60)

        return self._report_gen.generate(label=f"paper-trading-{label}")

    # ------------------------------------------------------------------
    # Internal pipeline step
    # ------------------------------------------------------------------

    def _process_tick(self, symbol: str) -> None:
        """Process one tick for a symbol through the full pipeline."""
        try:
            tick = self._provider.fetch(symbol)
            base = tick.price
            now = datetime.now(timezone.utc)

            # Build a 5-tick synthetic window with seeded variation
            rng = random.Random(hash(symbol) ^ self._day_counter)
            ticks = []
            for i in range(5):
                p = round(base * (1 + rng.uniform(-0.025, 0.025)), 4)
                ticks.append(MarketTick(
                    symbol=symbol,
                    price=p,
                    volume=tick.volume,
                    timestamp=now - timedelta(minutes=5 - i),
                    source=tick.source,
                ))

            # Publish FeatureVectorEvent
            fv = self._engineer.compute(ticks)
            fv_event = FeatureVectorEvent(
                event_type="data.feature_vector",
                symbol=fv.symbol,
                timestamp=fv.timestamp,
                features=dict(fv.features),
                source_quality=fv.source_quality,
            )
            self._bus.publish(fv_event)

            # Get strategy decision
            decision = self._strategy.evaluate(fv)

            # Guard: only SELL if we actually hold the position
            sym_upper = symbol.upper()
            has_position = sym_upper in self._entry_prices

            if decision.action == "SELL" and not has_position:
                return  # nothing to sell
            if decision.action == "BUY" and has_position:
                return  # already holding, skip second buy

            decision_event = DecisionEvent(
                event_type="intelligence.decision",
                symbol=decision.symbol,
                action=decision.action,
                confidence=decision.confidence,
                rationale=decision.rationale,
                strategy_id=decision.strategy_id,
            )
            self._bus.publish(decision_event)

            # For SELL: sell the exact quantity we hold
            if decision.action == "SELL":
                pos = self._portfolio_tracker.get_position(
                    sym_upper, self._price_feed.get(sym_upper, base)
                )
                if pos is None or pos.quantity < 0.01:
                    return

                from execution.models.order import Order
                sell_order = Order(
                    symbol=sym_upper,
                    action="SELL",
                    quantity=round(pos.quantity, 6),
                    order_type="MARKET",
                    strategy_id=decision.strategy_id,
                )
                fill = self._order_manager.execute(sell_order)
                self._portfolio_tracker.apply_fill(fill)
                ep = self._entry_prices.pop(sym_upper, fill.fill_price)
                self._metrics.record_fill(fill, entry_price=ep)
                self._journal.record(fill, decision_event)
                return

            # For BUY: risk-size the order
            order = self._risk_engine.approve(decision_event, self._portfolio)
            if order is None:
                return

            fill = self._order_manager.execute(order)
            self._portfolio_tracker.apply_fill(fill)
            self._entry_prices[sym_upper] = fill.fill_price

        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Tick failed for %s: %s", symbol, exc
            )
