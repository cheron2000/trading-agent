"""
Intelligence Layer (Athena) tests.
Covers: Decision, DecisionEvent, IStrategy compliance,
        SimpleRuleStrategy, LLMAgent, PromptBuilder, DecisionMemory.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from data.models.feature_vector import FeatureVector
from intelligence.agent.llm_agent import LLMAgent
from intelligence.agent.prompt_builder import PromptBuilder
from intelligence.context.memory import DecisionMemory
from intelligence.events.decision_event import DecisionEvent
from intelligence.models.decision import Decision
from intelligence.strategies.i_strategy import IStrategy
from intelligence.strategies.rule_based import SimpleRuleStrategy

TS = datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc)


def make_fv(pct: float, symbol: str = "AAPL", quality: float = 1.0) -> FeatureVector:
    return FeatureVector(
        symbol=symbol,
        timestamp=TS,
        features={
            "price_change_pct": pct,
            "price_latest": 100.0,
            "price_mean": 99.0,
            "price_std": 1.0,
            "volume_mean": 1000.0,
            "volume_total": 5000.0,
            "high": 102.0,
            "low": 97.0,
        },
        source_quality=quality,
    )


def make_decision(action: str = "HOLD") -> Decision:
    return Decision(
        symbol="AAPL",
        action=action,  # type: ignore[arg-type]
        confidence=0.5,
        rationale="test",
        strategy_id="test-strategy",
    )


# ---------------------------------------------------------------------------
# Decision model
# ---------------------------------------------------------------------------


class TestDecision:

    def test_valid_buy(self) -> None:
        d = make_decision("BUY")
        assert d.action == "BUY"

    def test_valid_sell(self) -> None:
        d = make_decision("SELL")
        assert d.action == "SELL"

    def test_valid_hold(self) -> None:
        d = make_decision("HOLD")
        assert d.action == "HOLD"

    def test_invalid_action_raises(self) -> None:
        with pytest.raises(ValueError, match="action"):
            Decision(
                symbol="AAPL",
                action="LONG",  # type: ignore[arg-type]
                confidence=0.5,
                rationale="x",
                strategy_id="s",
            )

    def test_confidence_above_1_raises(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            Decision(
                symbol="AAPL",
                action="BUY",
                confidence=1.1,
                rationale="x",
                strategy_id="s",
            )

    def test_confidence_below_0_raises(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            Decision(
                symbol="AAPL",
                action="BUY",
                confidence=-0.1,
                rationale="x",
                strategy_id="s",
            )

    def test_confidence_boundary_values(self) -> None:
        Decision(
            symbol="AAPL", action="BUY", confidence=0.0, rationale="x", strategy_id="s"
        )
        Decision(
            symbol="AAPL", action="BUY", confidence=1.0, rationale="x", strategy_id="s"
        )

    def test_empty_symbol_raises(self) -> None:
        with pytest.raises(ValueError):
            Decision(
                symbol="", action="BUY", confidence=0.5, rationale="x", strategy_id="s"
            )

    def test_empty_rationale_raises(self) -> None:
        with pytest.raises(ValueError):
            Decision(
                symbol="AAPL",
                action="BUY",
                confidence=0.5,
                rationale="",
                strategy_id="s",
            )

    def test_empty_strategy_id_raises(self) -> None:
        with pytest.raises(ValueError):
            Decision(
                symbol="AAPL",
                action="BUY",
                confidence=0.5,
                rationale="x",
                strategy_id="",
            )

    def test_immutability(self) -> None:
        d = make_decision()
        with pytest.raises((AttributeError, TypeError)):
            d.action = "BUY"  # type: ignore

    def test_to_dict(self) -> None:
        d = make_decision("BUY")
        dd = d.to_dict()
        assert dd["action"] == "BUY"
        assert dd["symbol"] == "AAPL"
        assert "confidence" in dd


# ---------------------------------------------------------------------------
# DecisionEvent
# ---------------------------------------------------------------------------


class TestDecisionEvent:

    def test_valid_creation(self) -> None:
        e = DecisionEvent(
            event_type="intelligence.decision",
            symbol="AAPL",
            action="BUY",
            confidence=0.8,
            rationale="bullish",
            strategy_id="rule-1",
        )
        assert e.event_type == "intelligence.decision"
        assert e.action == "BUY"

    def test_inherits_base_event_fields(self) -> None:
        e = DecisionEvent(
            event_type="intelligence.decision",
            symbol="AAPL",
            action="HOLD",
            confidence=0.5,
            rationale="neutral",
            strategy_id="rule-1",
        )
        assert hasattr(e, "event_id")
        assert hasattr(e, "occurred_at")
        assert hasattr(e, "schema_version")

    def test_invalid_action_raises(self) -> None:
        with pytest.raises(ValueError):
            DecisionEvent(
                event_type="intelligence.decision",
                symbol="AAPL",
                action="LONG",  # type: ignore[arg-type]
                confidence=0.5,
                rationale="x",
                strategy_id="s",
            )  # type: ignore

    def test_confidence_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError):
            DecisionEvent(
                event_type="intelligence.decision",
                symbol="AAPL",
                action="BUY",
                confidence=2.0,
                rationale="x",
                strategy_id="s",
            )

    def test_empty_symbol_raises(self) -> None:
        with pytest.raises(ValueError):
            DecisionEvent(
                event_type="intelligence.decision",
                symbol="",
                action="BUY",
                confidence=0.5,
                rationale="x",
                strategy_id="s",
            )

    def test_to_dict_extends_base(self) -> None:
        e = DecisionEvent(
            event_type="intelligence.decision",
            symbol="AAPL",
            action="SELL",
            confidence=0.7,
            rationale="bearish",
            strategy_id="s",
        )
        d = e.to_dict()
        assert "event_id" in d
        assert d["action"] == "SELL"
        assert d["symbol"] == "AAPL"


# ---------------------------------------------------------------------------
# IStrategy Protocol compliance
# ---------------------------------------------------------------------------


class TestIStrategyCompliance:

    def test_simple_rule_satisfies_protocol(self) -> None:
        assert isinstance(SimpleRuleStrategy(), IStrategy)

    def test_plain_object_does_not_satisfy(self) -> None:
        assert not isinstance(object(), IStrategy)


# ---------------------------------------------------------------------------
# SimpleRuleStrategy
# ---------------------------------------------------------------------------


class TestSimpleRuleStrategy:

    def test_default_threshold(self) -> None:
        s = SimpleRuleStrategy()
        assert s._threshold == 1.0

    def test_zero_threshold_raises(self) -> None:
        with pytest.raises(ValueError):
            SimpleRuleStrategy(threshold=0.0)

    def test_negative_threshold_raises(self) -> None:
        with pytest.raises(ValueError):
            SimpleRuleStrategy(threshold=-1.0)

    def test_buy_signal(self) -> None:
        s = SimpleRuleStrategy(threshold=1.0)
        d = s.evaluate(make_fv(pct=2.5))
        assert d.action == "BUY"
        assert d.symbol == "AAPL"

    def test_sell_signal(self) -> None:
        s = SimpleRuleStrategy(threshold=1.0)
        d = s.evaluate(make_fv(pct=-2.5))
        assert d.action == "SELL"

    def test_hold_signal(self) -> None:
        s = SimpleRuleStrategy(threshold=1.0)
        d = s.evaluate(make_fv(pct=0.5))
        assert d.action == "HOLD"

    def test_exact_threshold_is_hold(self) -> None:
        s = SimpleRuleStrategy(threshold=1.0)
        d = s.evaluate(make_fv(pct=1.0))
        assert d.action == "HOLD"

    def test_buy_confidence_capped_at_1(self) -> None:
        s = SimpleRuleStrategy(threshold=1.0)
        d = s.evaluate(make_fv(pct=100.0))
        assert d.confidence == 1.0

    def test_hold_confidence_decreases_with_pct(self) -> None:
        s = SimpleRuleStrategy(threshold=1.0)
        d_zero = s.evaluate(make_fv(pct=0.0))
        d_near = s.evaluate(make_fv(pct=0.9))
        assert d_zero.confidence > d_near.confidence

    def test_confidence_in_range(self) -> None:
        s = SimpleRuleStrategy(threshold=1.0)
        for pct in [-5.0, -1.0, 0.0, 0.5, 1.0, 5.0]:
            d = s.evaluate(make_fv(pct=pct))
            assert 0.0 <= d.confidence <= 1.0

    def test_none_feature_vector_raises(self) -> None:
        s = SimpleRuleStrategy()
        with pytest.raises(ValueError):
            s.evaluate(None)  # type: ignore

    def test_missing_price_change_pct_raises(self) -> None:
        s = SimpleRuleStrategy()
        fv = FeatureVector(
            symbol="AAPL", timestamp=TS, features={"high": 100.0}, source_quality=1.0
        )
        with pytest.raises(ValueError, match="price_change_pct"):
            s.evaluate(fv)

    def test_strategy_id_contains_threshold(self) -> None:
        s = SimpleRuleStrategy(threshold=2.5)
        assert "2.5" in s.strategy_id

    def test_decision_strategy_id_matches(self) -> None:
        s = SimpleRuleStrategy(threshold=1.0)
        d = s.evaluate(make_fv(pct=2.0))
        assert d.strategy_id == s.strategy_id


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------


class TestPromptBuilder:

    def test_build_returns_string(self) -> None:
        pb = PromptBuilder()
        prompt = pb.build(make_fv(pct=1.5))
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_build_contains_symbol(self) -> None:
        pb = PromptBuilder()
        prompt = pb.build(make_fv(pct=1.5, symbol="TSLA"))
        assert "TSLA" in prompt

    def test_build_contains_features(self) -> None:
        pb = PromptBuilder()
        prompt = pb.build(make_fv(pct=1.5))
        assert "price_change_pct" in prompt

    def test_build_none_raises(self) -> None:
        pb = PromptBuilder()
        with pytest.raises(ValueError):
            pb.build(None)  # type: ignore

    def test_build_deterministic(self) -> None:
        pb = PromptBuilder()
        fv = make_fv(pct=1.5)
        assert pb.build(fv) == pb.build(fv)


# ---------------------------------------------------------------------------
# LLMAgent
# ---------------------------------------------------------------------------


class TestLLMAgent:

    def _make_agent(self, response: str) -> LLMAgent:
        client = MagicMock()
        client.complete.return_value = response
        return LLMAgent(
            llm_client=client, prompt_builder=PromptBuilder(), strategy_id="llm-test"
        )

    def test_valid_buy_response(self) -> None:
        agent = self._make_agent(
            '{"action": "BUY", "confidence": 0.85, "rationale": "strong uptrend"}'
        )
        d = agent.evaluate(make_fv(pct=2.0))
        assert d.action == "BUY"
        assert d.confidence == pytest.approx(0.85)
        assert d.symbol == "AAPL"

    def test_valid_sell_response(self) -> None:
        agent = self._make_agent(
            '{"action": "SELL", "confidence": 0.7, "rationale": "bearish"}'
        )
        d = agent.evaluate(make_fv(pct=-2.0))
        assert d.action == "SELL"

    def test_valid_hold_response(self) -> None:
        agent = self._make_agent(
            '{"action": "HOLD", "confidence": 0.5, "rationale": "neutral"}'
        )
        d = agent.evaluate(make_fv(pct=0.0))
        assert d.action == "HOLD"

    def test_invalid_json_raises(self) -> None:
        agent = self._make_agent("not json at all")
        with pytest.raises(ValueError, match="JSON"):
            agent.evaluate(make_fv(pct=1.0))

    def test_invalid_action_raises(self) -> None:
        agent = self._make_agent(
            '{"action": "LONG", "confidence": 0.5, "rationale": "x"}'
        )
        with pytest.raises(ValueError, match="action"):
            agent.evaluate(make_fv(pct=1.0))

    def test_confidence_above_1_raises(self) -> None:
        agent = self._make_agent(
            '{"action": "BUY", "confidence": 1.5, "rationale": "x"}'
        )
        with pytest.raises(ValueError, match="confidence"):
            agent.evaluate(make_fv(pct=1.0))

    def test_missing_confidence_raises(self) -> None:
        agent = self._make_agent('{"action": "BUY", "rationale": "x"}')
        with pytest.raises(ValueError, match="confidence"):
            agent.evaluate(make_fv(pct=1.0))

    def test_empty_rationale_raises(self) -> None:
        agent = self._make_agent(
            '{"action": "BUY", "confidence": 0.8, "rationale": ""}'
        )
        with pytest.raises(ValueError, match="rationale"):
            agent.evaluate(make_fv(pct=1.0))

    def test_json_array_raises(self) -> None:
        agent = self._make_agent('[{"action": "BUY"}]')
        with pytest.raises(TypeError):
            agent.evaluate(make_fv(pct=1.0))

    def test_none_feature_vector_raises(self) -> None:
        agent = self._make_agent(
            '{"action": "BUY", "confidence": 0.8, "rationale": "x"}'
        )
        with pytest.raises(ValueError):
            agent.evaluate(None)  # type: ignore

    def test_empty_strategy_id_raises(self) -> None:
        with pytest.raises(ValueError):
            LLMAgent(
                llm_client=MagicMock(), prompt_builder=PromptBuilder(), strategy_id=""
            )

    def test_strategy_id_property(self) -> None:
        agent = self._make_agent("{}")
        assert agent.strategy_id == "llm-test"

    def test_decision_strategy_id_matches_agent(self) -> None:
        agent = self._make_agent(
            '{"action": "HOLD", "confidence": 0.5, "rationale": "neutral"}'
        )
        d = agent.evaluate(make_fv(pct=0.0))
        assert d.strategy_id == "llm-test"


# ---------------------------------------------------------------------------
# DecisionMemory
# ---------------------------------------------------------------------------


class TestDecisionMemory:

    def test_default_max_size(self) -> None:
        m = DecisionMemory()
        assert m.max_size == 100

    def test_custom_max_size(self) -> None:
        m = DecisionMemory(max_size=10)
        assert m.max_size == 10

    def test_zero_max_size_raises(self) -> None:
        with pytest.raises(ValueError):
            DecisionMemory(max_size=0)

    def test_add_and_size(self) -> None:
        m = DecisionMemory()
        m.add(make_decision("BUY"))
        assert m.size == 1

    def test_add_none_raises(self) -> None:
        m = DecisionMemory()
        with pytest.raises(ValueError):
            m.add(None)  # type: ignore

    def test_recent_returns_last_n(self) -> None:
        m = DecisionMemory()
        for action in ["BUY", "SELL", "HOLD", "BUY", "SELL"]:
            m.add(make_decision(action))
        recent = m.recent(3)
        assert len(recent) == 3
        assert recent[-1].action == "SELL"

    def test_recent_clamped_to_available(self) -> None:
        m = DecisionMemory()
        m.add(make_decision("BUY"))
        assert len(m.recent(10)) == 1

    def test_recent_zero_raises(self) -> None:
        m = DecisionMemory()
        with pytest.raises(ValueError):
            m.recent(0)

    def test_rolling_eviction(self) -> None:
        m = DecisionMemory(max_size=3)
        for action in ["BUY", "SELL", "HOLD", "BUY"]:
            m.add(make_decision(action))
        assert m.size == 3
        assert m.recent(3)[0].action == "SELL"

    def test_is_empty_true_initially(self) -> None:
        assert DecisionMemory().is_empty is True

    def test_is_empty_false_after_add(self) -> None:
        m = DecisionMemory()
        m.add(make_decision())
        assert m.is_empty is False

    def test_clear(self) -> None:
        m = DecisionMemory()
        m.add(make_decision())
        m.clear()
        assert m.size == 0
        assert m.is_empty is True
