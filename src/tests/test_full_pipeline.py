"""
Full system integration tests — AI Trading OS.

Wires all 7 layers together end-to-end:
  DataPipeline → FeatureVectorEvent → SimpleRuleStrategy → DecisionEvent
  → RiskEngine → Order → OrderManager → FillEvent
  → PortfolioTracker → TradeJournal → MetricsEngine → LiveView
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

import pytest

from analytics.journal.trade_journal import TradeJournal

# Analytics
from analytics.metrics.metrics_engine import MetricsEngine

# Communication
from communication.bus.event_bus import EventBus

# Dashboard
from dashboard.shell.live_view import LiveView
from data.events.feature_vector_event import FeatureVectorEvent
from data.features.feature_engineer import FeatureEngineer
from data.models.feature_vector import FeatureVector

# Data
from data.models.market_tick import MarketTick
from data.normalizers.market_normalizer import MarketNormalizer
from data.pipeline import DataPipeline
from execution.engine.order_manager import OrderManager
from execution.engine.portfolio_tracker import PortfolioTracker
from execution.events.fill_event import FillEvent

# Execution
from execution.models.order import Order
from execution.models.portfolio import Portfolio
from execution.risk.risk_engine import RiskEngine

# Foundation
from foundation.base_event import BaseEvent
from intelligence.events.decision_event import DecisionEvent

# Intelligence
from intelligence.models.decision import Decision
from intelligence.strategies.rule_based import SimpleRuleStrategy

TS = datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
PRICE_FEED = {"AAPL": 182.50, "MSFT": 374.25, "TSLA": 218.90}
INITIAL_CASH = 100_000.0


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def bus() -> EventBus:
    b = EventBus()
    yield b
    b.clear()


@pytest.fixture()
def portfolio() -> Portfolio:
    return Portfolio(initial_cash=INITIAL_CASH)


@pytest.fixture()
def tracker(portfolio: Portfolio) -> PortfolioTracker:
    return PortfolioTracker(portfolio)


@pytest.fixture()
def risk_engine() -> RiskEngine:
    return RiskEngine(price_feed=PRICE_FEED, max_position_pct=0.10, min_confidence=0.60)


@pytest.fixture()
def order_manager(bus: EventBus) -> OrderManager:
    return OrderManager(price_feed=PRICE_FEED, bus=bus)


@pytest.fixture()
def journal() -> TradeJournal:
    return TradeJournal()


@pytest.fixture()
def metrics() -> MetricsEngine:
    return MetricsEngine(initial_capital=INITIAL_CASH)


def make_decision_event(
    symbol: str = "AAPL",
    action: str = "BUY",
    confidence: float = 0.85,
    strategy_id: str = "simple-rule-t1.0",
) -> DecisionEvent:
    return DecisionEvent(
        event_type="intelligence.decision",
        symbol=symbol,
        action=action,  # type: ignore[arg-type]
        confidence=confidence,
        rationale="integration test decision",
        strategy_id=strategy_id,
    )


def make_feature_vector(symbol: str = "AAPL", pct: float = 2.5) -> FeatureVector:
    return FeatureVector(
        symbol=symbol,
        timestamp=TS,
        features={
            "price_change_pct": pct,
            "price_latest": PRICE_FEED[symbol],
            "price_mean": PRICE_FEED[symbol] * 0.99,
            "price_std": 1.5,
            "volume_mean": 1_000_000.0,
            "volume_total": 5_000_000.0,
            "high": PRICE_FEED[symbol] * 1.01,
            "low": PRICE_FEED[symbol] * 0.98,
        },
        source_quality=1.0,
    )


# ---------------------------------------------------------------------------
# Layer 3 → Layer 4: DataPipeline publishes FeatureVectorEvent
# ---------------------------------------------------------------------------


class TestDataToIntelligencePipeline:

    def test_data_pipeline_publishes_feature_vector_event(self, bus: EventBus) -> None:
        from typing import Any

        received: list[Any] = []
        bus.subscribe("data.feature_vector", received.append)

        tick = MarketTick(
            symbol="AAPL",
            price=182.50,
            volume=1_200_000.0,
            timestamp=TS,
            source="fixture",
        )
        provider_mock = type(
            "P",
            (),
            {
                "source_name": "fixture",
                "fetch": lambda self, s: tick,
            },
        )()

        pipeline = DataPipeline(
            provider=provider_mock,
            normalizer=MarketNormalizer(source="fixture"),
            engineer=FeatureEngineer(window_size=1),
            bus=bus,
        )
        event = pipeline.run("AAPL")

        assert isinstance(event, FeatureVectorEvent)
        assert event.symbol == "AAPL"
        assert len(received) == 1
        assert received[0].event_type == "data.feature_vector"

    def test_feature_vector_event_has_all_features(self, bus: EventBus) -> None:
        tick = MarketTick(
            symbol="AAPL",
            price=182.50,
            volume=1_200_000.0,
            timestamp=TS,
            source="fixture",
        )
        provider_mock = type(
            "P",
            (),
            {
                "source_name": "fixture",
                "fetch": lambda self, s: tick,
            },
        )()
        pipeline = DataPipeline(
            provider=provider_mock,
            normalizer=MarketNormalizer(source="fixture"),
            engineer=FeatureEngineer(window_size=1),
            bus=bus,
        )
        event = pipeline.run("AAPL")
        for key in ["price_latest", "price_mean", "high", "low", "volume_total"]:
            assert key in event.features


# ---------------------------------------------------------------------------
# Layer 4: SimpleRuleStrategy → DecisionEvent
# ---------------------------------------------------------------------------


class TestStrategyToDecision:

    def test_buy_signal_produces_buy_decision(self) -> None:
        strategy = SimpleRuleStrategy(threshold=1.0)
        fv = make_feature_vector("AAPL", pct=3.0)
        decision = strategy.evaluate(fv)
        assert decision.action == "BUY"
        assert decision.symbol == "AAPL"
        assert 0.0 <= decision.confidence <= 1.0

    def test_sell_signal_produces_sell_decision(self) -> None:
        strategy = SimpleRuleStrategy(threshold=1.0)
        fv = make_feature_vector("AAPL", pct=-3.0)
        decision = strategy.evaluate(fv)
        assert decision.action == "SELL"

    def test_hold_signal_produces_hold_decision(self) -> None:
        strategy = SimpleRuleStrategy(threshold=1.0)
        fv = make_feature_vector("AAPL", pct=0.3)
        decision = strategy.evaluate(fv)
        assert decision.action == "HOLD"

    def test_decision_event_wraps_decision_correctly(self) -> None:
        strategy = SimpleRuleStrategy(threshold=1.0)
        fv = make_feature_vector("AAPL", pct=2.5)
        d = strategy.evaluate(fv)
        event = DecisionEvent(
            event_type="intelligence.decision",
            symbol=d.symbol,
            action=d.action,
            confidence=d.confidence,
            rationale=d.rationale,
            strategy_id=d.strategy_id,
        )
        assert event.event_type == "intelligence.decision"
        assert event.action == "BUY"
        assert hasattr(event, "event_id")


# ---------------------------------------------------------------------------
# Layer 5: RiskEngine → Order
# ---------------------------------------------------------------------------


class TestRiskEngineApproval:

    def test_buy_decision_approved(
        self, risk_engine: RiskEngine, portfolio: Portfolio
    ) -> None:
        decision = make_decision_event("AAPL", "BUY", confidence=0.85)
        order = risk_engine.approve(decision, portfolio)
        assert order is not None
        assert isinstance(order, Order)
        assert order.action == "BUY"
        assert order.symbol == "AAPL"

    def test_hold_decision_rejected(
        self, risk_engine: RiskEngine, portfolio: Portfolio
    ) -> None:
        decision = make_decision_event("AAPL", "HOLD", confidence=0.9)
        assert risk_engine.approve(decision, portfolio) is None

    def test_low_confidence_rejected(
        self, risk_engine: RiskEngine, portfolio: Portfolio
    ) -> None:
        decision = make_decision_event("AAPL", "BUY", confidence=0.3)
        assert risk_engine.approve(decision, portfolio) is None

    def test_unknown_symbol_rejected(
        self, risk_engine: RiskEngine, portfolio: Portfolio
    ) -> None:
        decision = make_decision_event("UNKNOWN", "BUY", confidence=0.9)
        assert risk_engine.approve(decision, portfolio) is None

    def test_order_quantity_calculated_correctly(
        self, risk_engine: RiskEngine, portfolio: Portfolio
    ) -> None:
        decision = make_decision_event("AAPL", "BUY", confidence=0.85)
        order = risk_engine.approve(decision, portfolio)
        expected_qty = round((INITIAL_CASH * 0.10) / PRICE_FEED["AAPL"], 6)
        assert order.quantity == pytest.approx(expected_qty)

    def test_sell_decision_approved(
        self, risk_engine: RiskEngine, portfolio: Portfolio
    ) -> None:
        decision = make_decision_event("AAPL", "SELL", confidence=0.80)
        order = risk_engine.approve(decision, portfolio)
        assert order is not None
        assert order.action == "SELL"


# ---------------------------------------------------------------------------
# Layer 5: OrderManager → FillEvent
# ---------------------------------------------------------------------------


class TestOrderManagerExecution:

    def test_execute_returns_fill_event(self, order_manager: OrderManager) -> None:
        order = Order(
            symbol="AAPL",
            action="BUY",
            quantity=10.0,
            order_type="MARKET",
            strategy_id="test",
        )
        fill = order_manager.execute(order)
        assert isinstance(fill, FillEvent)
        assert fill.symbol == "AAPL"
        assert fill.action == "BUY"
        assert fill.fill_price == PRICE_FEED["AAPL"]

    def test_execute_publishes_fill_event_on_bus(
        self, bus: EventBus, order_manager: OrderManager
    ) -> None:
        received = []
        bus.subscribe("execution.fill", received.append)
        order = Order(
            symbol="AAPL",
            action="BUY",
            quantity=5.0,
            order_type="MARKET",
            strategy_id="test",
        )
        order_manager.execute(order)
        assert len(received) == 1
        assert received[0].event_type == "execution.fill"

    def test_execute_unknown_symbol_raises(self, order_manager: OrderManager) -> None:
        order = Order(
            symbol="UNKNOWN",
            action="BUY",
            quantity=1.0,
            order_type="MARKET",
            strategy_id="test",
        )
        with pytest.raises(ValueError):
            order_manager.execute(order)

    def test_live_mode_raises(self, bus: EventBus) -> None:
        with pytest.raises(NotImplementedError):
            OrderManager(price_feed=PRICE_FEED, bus=bus, live_mode=True)


# ---------------------------------------------------------------------------
# Layer 5: PortfolioTracker
# ---------------------------------------------------------------------------


class TestPortfolioTracker:

    def test_apply_buy_fill_updates_position(self, tracker: PortfolioTracker) -> None:
        fill = FillEvent(
            event_type="execution.fill",
            order_id="o1",
            symbol="AAPL",
            action="BUY",
            quantity=10.0,
            fill_price=182.50,
            timestamp=TS,
        )
        tracker.apply_fill(fill)
        pos = tracker.get_position("AAPL", 182.50)
        assert pos is not None
        assert pos.quantity == pytest.approx(10.0)
        assert pos.avg_entry_price == pytest.approx(182.50)

    def test_apply_buy_deducts_cash(self, tracker: PortfolioTracker) -> None:
        fill = FillEvent(
            event_type="execution.fill",
            order_id="o1",
            symbol="AAPL",
            action="BUY",
            quantity=10.0,
            fill_price=182.50,
            timestamp=TS,
        )
        tracker.apply_fill(fill)
        expected_cash = INITIAL_CASH - (10.0 * 182.50)
        assert tracker.cash == pytest.approx(expected_cash)

    def test_apply_sell_fill_removes_position(self, tracker: PortfolioTracker) -> None:
        buy = FillEvent(
            event_type="execution.fill",
            order_id="o1",
            symbol="AAPL",
            action="BUY",
            quantity=10.0,
            fill_price=182.50,
            timestamp=TS,
        )
        sell = FillEvent(
            event_type="execution.fill",
            order_id="o2",
            symbol="AAPL",
            action="SELL",
            quantity=10.0,
            fill_price=190.0,
            timestamp=TS,
        )
        tracker.apply_fill(buy)
        tracker.apply_fill(sell)
        assert tracker.get_position("AAPL", 190.0) is None

    def test_portfolio_value_correct(self, tracker: PortfolioTracker) -> None:
        fill = FillEvent(
            event_type="execution.fill",
            order_id="o1",
            symbol="AAPL",
            action="BUY",
            quantity=10.0,
            fill_price=182.50,
            timestamp=TS,
        )
        tracker.apply_fill(fill)
        value = tracker.portfolio_value({"AAPL": 200.0})
        expected = (INITIAL_CASH - 10.0 * 182.50) + 10.0 * 200.0
        assert value == pytest.approx(expected)

    def test_apply_none_fill_raises(self, tracker: PortfolioTracker) -> None:
        with pytest.raises(ValueError):
            tracker.apply_fill(None)  # type: ignore


# ---------------------------------------------------------------------------
# Layer 6: TradeJournal
# ---------------------------------------------------------------------------


class TestTradeJournal:

    def _make_fill(self) -> FillEvent:
        return FillEvent(
            event_type="execution.fill",
            order_id="o1",
            symbol="AAPL",
            action="BUY",
            quantity=10.0,
            fill_price=182.50,
            timestamp=TS,
        )

    def test_record_creates_entry(self, journal: TradeJournal) -> None:
        fill = self._make_fill()
        decision = make_decision_event()
        entry = journal.record(fill, decision)
        assert entry.sequence == 1
        assert entry.fill is fill
        assert journal.entry_count == 1

    def test_verify_integrity_empty_journal(self, journal: TradeJournal) -> None:
        assert journal.verify_integrity() is True

    def test_verify_integrity_after_records(self, journal: TradeJournal) -> None:
        fill = self._make_fill()
        decision = make_decision_event()
        journal.record(fill, decision)
        journal.record(fill, decision)
        assert journal.verify_integrity() is True

    def test_hash_chain_links_entries(self, journal: TradeJournal) -> None:
        fill = self._make_fill()
        decision = make_decision_event()
        e1 = journal.record(fill, decision)
        e2 = journal.record(fill, decision)
        assert e2.prev_hash == e1.entry_hash

    def test_first_entry_prev_hash_is_genesis(self, journal: TradeJournal) -> None:
        fill = self._make_fill()
        decision = make_decision_event()
        entry = journal.record(fill, decision)
        assert entry.prev_hash == TradeJournal.GENESIS_HASH


# ---------------------------------------------------------------------------
# Layer 6: MetricsEngine
# ---------------------------------------------------------------------------


class TestMetricsEngine:

    def _make_fill(self, action: str, price: float, qty: float = 10.0) -> FillEvent:
        return FillEvent(
            event_type="execution.fill",
            order_id="o1",
            symbol="AAPL",
            action=action,  # type: ignore[arg-type]
            quantity=qty,
            fill_price=price,
            timestamp=TS,
        )

    def test_compute_empty_returns_zero_metrics(self, metrics: MetricsEngine) -> None:
        m = metrics.compute()
        assert m.total_trades == 0
        assert m.total_pnl == 0.0
        assert m.win_rate == 0.0

    def test_profitable_sell_recorded(self, metrics: MetricsEngine) -> None:
        fill = self._make_fill("SELL", price=200.0)
        metrics.record_fill(fill, entry_price=182.50)
        m = metrics.compute()
        assert m.total_trades == 1
        assert m.total_pnl == pytest.approx((200.0 - 182.50) * 10.0)
        assert m.win_rate == 1.0

    def test_losing_sell_recorded(self, metrics: MetricsEngine) -> None:
        fill = self._make_fill("SELL", price=170.0)
        metrics.record_fill(fill, entry_price=182.50)
        m = metrics.compute()
        assert m.total_pnl < 0
        assert m.win_rate == 0.0

    def test_buy_fill_not_counted_as_trade(self, metrics: MetricsEngine) -> None:
        fill = self._make_fill("BUY", price=182.50)
        metrics.record_fill(fill, entry_price=182.50)
        m = metrics.compute()
        assert m.total_trades == 0

    def test_sharpe_zero_for_single_trade(self, metrics: MetricsEngine) -> None:
        fill = self._make_fill("SELL", price=200.0)
        metrics.record_fill(fill, entry_price=182.50)
        m = metrics.compute()
        assert m.sharpe_ratio == 0.0

    def test_sharpe_nonzero_for_multiple_trades(self, metrics: MetricsEngine) -> None:
        for price in [200.0, 195.0, 210.0]:
            fill = self._make_fill("SELL", price=price)
            metrics.record_fill(fill, entry_price=182.50)
        m = metrics.compute()
        assert m.sharpe_ratio != 0.0

    def test_max_drawdown_zero_with_no_losses(self, metrics: MetricsEngine) -> None:
        for price in [190.0, 195.0, 200.0]:
            fill = self._make_fill("SELL", price=price)
            metrics.record_fill(fill, entry_price=182.50)
        m = metrics.compute()
        assert m.max_drawdown == pytest.approx(0.0)

    def test_to_dict_has_all_keys(self, metrics: MetricsEngine) -> None:
        m = metrics.compute()
        d = m.to_dict()
        for key in [
            "total_trades",
            "total_pnl",
            "total_return",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
        ]:
            assert key in d


# ---------------------------------------------------------------------------
# Layer 7: LiveView
# ---------------------------------------------------------------------------


class TestLiveView:

    def test_start_subscribes_to_patterns(self, bus: EventBus) -> None:
        output = io.StringIO()
        view = LiveView(bus=bus, output=output)
        view.start()
        assert bus.subscription_count == len(LiveView._SUBSCRIBED_PATTERNS)
        view.stop()

    def test_stop_unsubscribes(self, bus: EventBus) -> None:
        output = io.StringIO()
        view = LiveView(bus=bus, output=output)
        view.start()
        view.stop()
        assert bus.subscription_count == 0

    def test_receives_feature_vector_event(self, bus: EventBus) -> None:
        output = io.StringIO()
        view = LiveView(bus=bus, output=output)
        view.start()
        bus.publish(BaseEvent(event_type="data.feature_vector"))
        assert view.event_count == 1
        view.stop()

    def test_receives_decision_event(self, bus: EventBus) -> None:
        output = io.StringIO()
        view = LiveView(bus=bus, output=output)
        view.start()
        bus.publish(BaseEvent(event_type="intelligence.decision"))
        assert view.event_count == 1
        view.stop()

    def test_receives_fill_event(self, bus: EventBus) -> None:
        output = io.StringIO()
        view = LiveView(bus=bus, output=output)
        view.start()
        bus.publish(BaseEvent(event_type="execution.fill"))
        assert view.event_count == 1
        view.stop()

    def test_event_count_increments(self, bus: EventBus) -> None:
        output = io.StringIO()
        view = LiveView(bus=bus, output=output)
        view.start()
        for et in ["data.feature_vector", "intelligence.decision", "execution.fill"]:
            bus.publish(BaseEvent(event_type=et))
        assert view.event_count == 3
        view.stop()


# ---------------------------------------------------------------------------
# Full end-to-end pipeline test
# ---------------------------------------------------------------------------


class TestFullEndToEndPipeline:

    def test_full_pipeline_buy_flow(self) -> None:
        """
        Full flow: FeatureVector → Strategy → DecisionEvent → RiskEngine
        → Order → OrderManager → FillEvent → PortfolioTracker
        → TradeJournal → MetricsEngine → LiveView receives all events.
        """
        bus = EventBus()
        output = io.StringIO()
        view = LiveView(bus=bus, output=output)
        view.start()

        portfolio = Portfolio(initial_cash=INITIAL_CASH)
        tracker = PortfolioTracker(portfolio)
        risk = RiskEngine(
            price_feed=PRICE_FEED, max_position_pct=0.10, min_confidence=0.60
        )
        om = OrderManager(price_feed=PRICE_FEED, bus=bus)
        journal = TradeJournal()
        metrics = MetricsEngine(initial_capital=INITIAL_CASH)

        # Step 1 — Strategy evaluates feature vector
        strategy = SimpleRuleStrategy(threshold=1.0)
        fv = make_feature_vector("AAPL", pct=3.0)
        decision = strategy.evaluate(fv)
        assert decision.action == "BUY"

        # Step 2 — Wrap in DecisionEvent and publish
        decision_event = DecisionEvent(
            event_type="intelligence.decision",
            symbol=decision.symbol,
            action=decision.action,
            confidence=decision.confidence,
            rationale=decision.rationale,
            strategy_id=decision.strategy_id,
        )
        bus.publish(decision_event)

        # Step 3 — Risk engine approves
        order = risk.approve(decision_event, portfolio)
        assert order is not None
        assert order.action == "BUY"

        # Step 4 — Execute order → FillEvent published on bus
        fill = om.execute(order)
        assert isinstance(fill, FillEvent)
        assert fill.symbol == "AAPL"

        # Step 5 — Portfolio tracker applies fill
        tracker.apply_fill(fill)
        pos = tracker.get_position("AAPL", PRICE_FEED["AAPL"])
        assert pos is not None
        assert pos.quantity == pytest.approx(order.quantity)

        # Step 6 — Journal records the trade
        entry = journal.record(fill, decision_event)
        assert entry.sequence == 1
        assert journal.verify_integrity() is True

        # Step 7 — Metrics (BUY only — no realized P&L yet)
        metrics.record_fill(fill, entry_price=PRICE_FEED["AAPL"])
        m = metrics.compute()
        assert m.total_trades == 0  # BUY not counted until SELL

        # Step 8 — LiveView received decision + fill events
        assert view.event_count >= 2

        view.stop()
        bus.clear()

    def test_runner_logs_buy_fills_in_the_trade_journal(self) -> None:
        from paper_trading.runner import PaperTradingRunner

        runner = PaperTradingRunner(initial_capital=INITIAL_CASH, run_days=1)

        class FakeProvider:
            def __init__(self) -> None:
                self.source_name = "fixture"

            def fetch(self, symbol: str) -> MarketTick:
                return MarketTick(
                    symbol=symbol,
                    price=100.0,
                    volume=1_000.0,
                    timestamp=datetime.now(timezone.utc),
                    source="fixture",
                )

        runner._provider = FakeProvider()  # type: ignore[assignment]
        runner._strategy.evaluate = lambda fv: Decision(  # type: ignore[assignment]
            symbol="AAPL",
            action="BUY",
            confidence=0.95,
            rationale="test",
            strategy_id="test-strategy",
        )

        runner._process_tick("AAPL")

        assert runner._journal.entry_count == 1
        assert runner._journal.verify_integrity() is True
        assert runner._journal.entries()[0].fill.action == "BUY"

    def test_full_pipeline_buy_then_sell_realizes_pnl(self) -> None:
        bus = EventBus()
        portfolio = Portfolio(initial_cash=INITIAL_CASH)
        tracker = PortfolioTracker(portfolio)
        risk = RiskEngine(
            price_feed=PRICE_FEED, max_position_pct=0.10, min_confidence=0.60
        )
        om = OrderManager(price_feed=PRICE_FEED, bus=bus)
        metrics = MetricsEngine(initial_capital=INITIAL_CASH)
        journal = TradeJournal()

        # BUY
        buy_decision = make_decision_event("AAPL", "BUY", confidence=0.85)
        buy_order = risk.approve(buy_decision, portfolio)
        buy_fill = om.execute(buy_order)
        tracker.apply_fill(buy_fill)
        metrics.record_fill(buy_fill, entry_price=PRICE_FEED["AAPL"])
        journal.record(buy_fill, buy_decision)

        # SELL at higher price
        sell_price_feed = {"AAPL": 200.0}
        sell_om = OrderManager(price_feed=sell_price_feed, bus=bus)
        _sell_risk = RiskEngine(
            price_feed=sell_price_feed, max_position_pct=0.10, min_confidence=0.60
        )
        sell_decision = make_decision_event("AAPL", "SELL", confidence=0.80)
        sell_order = Order(
            symbol="AAPL",
            action="SELL",
            quantity=buy_order.quantity,
            order_type="MARKET",
            strategy_id="test",
        )
        sell_fill = sell_om.execute(sell_order)
        tracker.apply_fill(sell_fill)
        metrics.record_fill(sell_fill, entry_price=PRICE_FEED["AAPL"])
        journal.record(sell_fill, sell_decision)

        # Verify P&L
        m = metrics.compute()
        assert m.total_trades == 1
        assert m.total_pnl > 0
        assert m.win_rate == 1.0

        # Verify journal integrity
        assert journal.verify_integrity() is True
        assert journal.entry_count == 2

        # Verify position is flat
        assert tracker.get_position("AAPL", 200.0) is None

        bus.clear()
