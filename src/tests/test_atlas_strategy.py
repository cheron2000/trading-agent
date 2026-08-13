"""
src/tests/test_atlas_strategy.py
=================================

Unit tests for AtlasStrategy prompt generation, JSON response parsing, and error handling.
"""

from datetime import datetime, timezone
import pytest
from unittest.mock import patch
from data.models.feature_vector import FeatureVector
from intelligence.strategies.atlas_strategy import AtlasStrategy


def test_atlas_strategy_init():
    strat = AtlasStrategy(groq_api_key="gsk_test123", groq_model="llama-3.1-8b-instant")
    assert strat.strategy_id == "ATLAS-LLM"
    status = strat.get_current_key_status()
    assert status["total_keys"] == 1
    assert status["model"] == "llama-3.1-8b-instant"

    strat_multi = AtlasStrategy(groq_api_key=["gsk_key1", "gsk_key2"])
    assert strat_multi.get_current_key_status()["total_keys"] == 2

    with pytest.raises(ValueError):
        AtlasStrategy(groq_api_key=[])


def test_build_atlas_prompt():
    strat = AtlasStrategy(groq_api_key="gsk_test123")
    fv = FeatureVector(
        symbol="AAPL",
        timestamp=datetime.now(timezone.utc),
        features={
            "price_latest": 150.0,
            "vwap": 149.5,
            "rsi": 62.0,
            "macd_line": 0.5,
            "macd_signal": 0.2,
            "macd_histogram": 0.3,
            "bb_upper": 155.0,
            "bb_middle": 150.0,
            "bb_lower": 145.0,
            "bb_position": 0.5,
            "atr": 2.5,
            "atr_ratio": 1.0,
            "regime_label": "trending",
            "regime_confidence": 0.85,
            "adx": 30.0,
        },
        source_quality=1.0,
    )

    pos_ctx = {
        "has_position": True,
        "entry_price": 145.0,
        "pnl_pct": 3.45,
        "hold_cycles": 4,
        "news_context": "Apple reports strong earnings.",
        "daily_trend": "BULLISH",
    }

    prompt = strat._build_atlas_prompt(fv, pos_ctx)
    assert "Asset: AAPL" in prompt
    assert "Price: $150.00" in prompt
    assert "RSI(14): 62.0" in prompt
    assert "Status: HOLDING" in prompt
    assert "Apple reports strong earnings." in prompt


def test_parse_atlas_response_valid():
    strat = AtlasStrategy(groq_api_key="gsk_test123")
    fv = FeatureVector(
        symbol="TSLA",
        timestamp=datetime.now(timezone.utc),
        features={"adx": 30.0, "rsi": 55.0, "bb_position": 0.5},
        source_quality=1.0,
    )

    json_str = """
    {
        "asset": "TSLA",
        "action": "BUY",
        "confidence": 85,
        "regime_used": "TRENDING",
        "reasoning": "Strong MACD bullish crossover."
    }
    """

    decision = strat._parse_atlas_response(fv, json_str, "MockEngine")
    assert decision.symbol == "TSLA"
    assert decision.action == "BUY"
    assert decision.confidence == 0.85
    assert "[MockEngine]" in decision.rationale
    assert "Strong MACD bullish crossover." in decision.rationale


def test_parse_atlas_response_invalid_json():
    strat = AtlasStrategy(groq_api_key="gsk_test123")
    fv = FeatureVector(
        symbol="GOOGL",
        timestamp=datetime.now(timezone.utc),
        features={"adx": 10.0, "rsi": 50.0, "bb_position": 0.5},
        source_quality=1.0,
    )

    bad_text = "This is not JSON text at all."
    decision = strat._parse_atlas_response(fv, bad_text, "MockEngine")

    assert decision.symbol == "GOOGL"
    assert decision.action in ("BUY", "HOLD")


@patch.object(AtlasStrategy, "_call_groq")
def test_evaluate_with_context(mock_groq):
    strat = AtlasStrategy(groq_api_key="gsk_test123")
    mock_groq.return_value = (
        '{"action": "SELL", "confidence": 75, "reasoning": "Overbought condition."}',
        "Groq test-model",
    )

    fv = FeatureVector(
        symbol="MSFT",
        timestamp=datetime.now(timezone.utc),
        features={"adx": 35.0, "rsi": 75.0, "bb_position": 0.9},
        source_quality=1.0,
    )

    decision = strat.evaluate_with_context(fv)
    assert decision.symbol == "MSFT"
    assert decision.action == "SELL"
    assert decision.confidence == 0.75
