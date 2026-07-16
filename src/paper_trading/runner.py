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

from datetime import datetime, timezone
from pathlib import Path

from communication.bus.event_bus import EventBus
from data.features.feature_engineer import FeatureEngineer
from data.normalizers.market_normalizer import MarketNormalizer
from data.pipeline import DataPipeline
from data.providers.market_provider import MarketDataProvider
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
    """Runs a paper trading simulation using fixture data.

    Wires all 7 layers together. Uses only fixture data — no live calls.

    Usage::

        runner = PaperTradingRunner(initial_capital=100_000.0, run_days=30)
        report = runner.run()
        assert report["journal_integrity"] == True
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        run_days: int = 30,
        threshold: float = 0.5,
        fixture_path: Path | str = _DEFAULT_FIXTURE,
    ) -> None:
        """
        Args:
            initial_capital: Starting cash for the portfolio.
            run_days:        Number of simulated trading days.
            threshold:       SimpleRuleStrategy price_change_pct threshold.
            fixture_path:    Path to the market tick JSON fixture.

        Raises:
            ValueError: If initial_capital <= 0 or run_days < 1.
        """
        if initial_capital <= 0:
            raise ValueError("initial_capital must be > 0.")
        if run_days < 1:
            raise ValueError("run_days must be >= 1.")

        self._run_days = run_days
        self._fixture_path = Path(fixture_path)

        # ------------------------------------------------------------------
        # Wire up all layers
        # ------------------------------------------------------------------
        self._bus = EventBus()

        # L3 — Data
        self._provider = MarketDataProvider(fixture_path=self._fixture_path)
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
        # Price feed built from fixture at construction time
        self._price_feed: dict[str, float] = {
            sym: self._provider.fetch(sym).price
            for sym in _FIXTURE_SYMBOLS
        }
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """Execute the full paper trading simulation.

        Iterates over symbols × run_days, processing each tick through
        the full pipeline.

        Returns:
            ReportGenerator.generate() dict with final metrics.
        """
        label = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for day in range(self._run_days):
            for symbol in _FIXTURE_SYMBOLS:
                self._process_tick(symbol)

        return self._report_gen.generate(label=f"paper-trading-{label}")

    # ------------------------------------------------------------------
    # Internal pipeline step
    # ------------------------------------------------------------------

    def _process_tick(self, symbol: str) -> None:
        """Process one tick for a symbol through the full pipeline."""
        try:
            # L3 — fetch + engineer → FeatureVectorEvent
            fv_event = self._pipeline.run(symbol)

            # L4 — evaluate strategy → Decision
            from data.models.feature_vector import FeatureVector
            fv = FeatureVector(
                symbol=fv_event.symbol,
                timestamp=fv_event.timestamp,
                features=fv_event.features,
                source_quality=fv_event.source_quality,
            )
            decision = self._strategy.evaluate(fv)

            # Wrap decision in DecisionEvent for RiskEngine
            decision_event = DecisionEvent(
                event_type="intelligence.decision",
                symbol=decision.symbol,
                action=decision.action,
                confidence=decision.confidence,
                rationale=decision.rationale,
                strategy_id=decision.strategy_id,
            )
            self._bus.publish(decision_event)

            # L5 — risk gate
            order = self._risk_engine.approve(decision_event, self._portfolio)
            if order is None:
                return

            # Record entry price before fill
            entry_price = self._price_feed.get(symbol.upper(), order.quantity)

            # Execute paper fill
            fill = self._order_manager.execute(order)

            # Update portfolio
            self._portfolio_tracker.apply_fill(fill)

            # L6 — record metrics + journal (only for SELL fills for P&L)
            if fill.action == "SELL":
                ep = self._entry_prices.get(symbol.upper(), fill.fill_price)
                self._metrics.record_fill(fill, entry_price=ep)
                self._journal.record(fill, decision_event)
            else:
                # Track entry price for future SELL
                self._entry_prices[symbol.upper()] = fill.fill_price

        except Exception as exc:
            # Log but don't crash — simulation must continue on single-tick failures
            import logging
            logging.getLogger(__name__).warning(
                "Tick failed for %s: %s", symbol, exc
            )
