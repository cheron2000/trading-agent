"""
Data Layer (Orion) — Step 2 tests.
Covers: FeatureEngineer (deterministic features, edge cases),
        DataPipeline (integration with stubs).
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from data.events.feature_vector_event import FeatureVectorEvent
from data.features.feature_engineer import FeatureEngineer
from data.models.feature_vector import FeatureVector
from data.models.market_tick import MarketTick
from data.normalizers.market_normalizer import MarketNormalizer
from data.pipeline import DataPipeline

TS = datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc)


def make_tick(
    price: float,
    volume: float = 1000.0,
    symbol: str = "AAPL",
    ts: datetime = TS,
) -> MarketTick:
    return MarketTick(
        symbol=symbol, price=price, volume=volume, timestamp=ts, source="fixture"
    )


# ---------------------------------------------------------------------------
# FeatureEngineer — constructor
# ---------------------------------------------------------------------------


class TestFeatureEngineerInit:

    def test_default_window_size(self) -> None:
        fe = FeatureEngineer()
        assert fe.window_size == 26

    def test_custom_window_size(self) -> None:
        fe = FeatureEngineer(window_size=5)
        assert fe.window_size == 5

    def test_window_size_zero_raises(self) -> None:
        with pytest.raises(ValueError):
            FeatureEngineer(window_size=0)

    def test_window_size_negative_raises(self) -> None:
        with pytest.raises(ValueError):
            FeatureEngineer(window_size=-1)

    def test_window_size_one_allowed(self) -> None:
        fe = FeatureEngineer(window_size=1)
        assert fe.window_size == 1


# ---------------------------------------------------------------------------
# FeatureEngineer — compute() validation
# ---------------------------------------------------------------------------


class TestFeatureEngineerValidation:

    def test_empty_ticks_raises(self) -> None:
        fe = FeatureEngineer()
        with pytest.raises(ValueError, match="empty"):
            fe.compute([])

    def test_mixed_symbols_raises(self) -> None:
        fe = FeatureEngineer()
        ticks = [make_tick(100.0, symbol="AAPL"), make_tick(200.0, symbol="MSFT")]
        with pytest.raises(ValueError, match="symbol"):
            fe.compute(ticks)

    def test_single_tick_allowed(self) -> None:
        fe = FeatureEngineer(window_size=1)
        fv = fe.compute([make_tick(100.0)])
        assert isinstance(fv, FeatureVector)


# ---------------------------------------------------------------------------
# FeatureEngineer — deterministic feature values
# ---------------------------------------------------------------------------


class TestFeatureEngineerFeatureValues:

    def setup_method(self) -> None:
        self.prices = [100.0, 102.0, 101.0, 103.0, 105.0]
        self.volumes = [1000.0, 1100.0, 900.0, 1200.0, 1050.0]
        self.ticks = [make_tick(p, v) for p, v in zip(self.prices, self.volumes)]
        self.fe = FeatureEngineer(window_size=5)
        self.fv = self.fe.compute(self.ticks)

    def test_price_latest(self) -> None:
        assert self.fv.features["price_latest"] == 105.0

    def test_price_mean(self) -> None:
        expected = statistics.mean(self.prices)
        assert self.fv.features["price_mean"] == pytest.approx(expected)

    def test_price_std(self) -> None:
        expected = statistics.pstdev(self.prices)
        assert self.fv.features["price_std"] == pytest.approx(expected)

    def test_price_change_pct(self) -> None:
        expected = (105.0 - 100.0) / 100.0 * 100.0
        assert self.fv.features["price_change_pct"] == pytest.approx(expected)

    def test_volume_mean(self) -> None:
        expected = statistics.mean(self.volumes)
        assert self.fv.features["volume_mean"] == pytest.approx(expected)

    def test_volume_total(self) -> None:
        expected = sum(self.volumes)
        assert self.fv.features["volume_total"] == pytest.approx(expected)

    def test_high(self) -> None:
        assert self.fv.features["high"] == 105.0

    def test_low(self) -> None:
        assert self.fv.features["low"] == 100.0

    def test_all_eight_features_present(self) -> None:
        expected_keys = {
            "price_latest",
            "price_mean",
            "price_std",
            "price_change_pct",
            "volume_mean",
            "volume_total",
            "high",
            "low",
        }
        assert expected_keys.issubset(set(self.fv.features.keys()))

    def test_deterministic_same_input_same_output(self) -> None:
        fv2 = self.fe.compute(self.ticks)
        assert self.fv.features == fv2.features


# ---------------------------------------------------------------------------
# FeatureEngineer — single tick edge cases
# ---------------------------------------------------------------------------


class TestFeatureEngineerSingleTick:

    def test_price_std_is_zero_for_single_tick(self) -> None:
        fe = FeatureEngineer(window_size=1)
        fv = fe.compute([make_tick(150.0)])
        assert fv.features["price_std"] == 0.0

    def test_price_change_pct_is_zero_for_single_tick(self) -> None:
        fe = FeatureEngineer(window_size=1)
        fv = fe.compute([make_tick(150.0)])
        assert fv.features["price_change_pct"] == 0.0

    def test_high_equals_low_for_single_tick(self) -> None:
        fe = FeatureEngineer(window_size=1)
        fv = fe.compute([make_tick(150.0)])
        assert fv.features["high"] == fv.features["low"] == 150.0


# ---------------------------------------------------------------------------
# FeatureEngineer — source_quality
# ---------------------------------------------------------------------------


class TestFeatureEngineerSourceQuality:

    def test_full_window_quality_is_1(self) -> None:
        fe = FeatureEngineer(window_size=3)
        ticks = [make_tick(100.0), make_tick(101.0), make_tick(102.0)]
        fv = fe.compute(ticks)
        assert fv.source_quality == 1.0

    def test_partial_window_quality_less_than_1(self) -> None:
        fe = FeatureEngineer(window_size=10)
        ticks = [make_tick(100.0), make_tick(101.0)]  # 2 of 10
        fv = fe.compute(ticks)
        assert fv.source_quality == pytest.approx(0.2)

    def test_over_full_window_capped_at_1(self) -> None:
        fe = FeatureEngineer(window_size=2)
        ticks = [make_tick(float(p)) for p in range(1, 6)]  # 5 ticks, window=2
        fv = fe.compute(ticks)
        assert fv.source_quality == 1.0

    def test_timestamp_is_latest_tick(self) -> None:
        from datetime import timedelta

        ts1 = TS
        ts2 = TS + timedelta(seconds=60)
        ticks = [make_tick(100.0, ts=ts1), make_tick(101.0, ts=ts2)]
        fe = FeatureEngineer(window_size=2)
        fv = fe.compute(ticks)
        assert fv.timestamp == ts2

    def test_symbol_propagated(self) -> None:
        fe = FeatureEngineer(window_size=1)
        fv = fe.compute([make_tick(100.0, symbol="TSLA")])
        assert fv.symbol == "TSLA"


# ---------------------------------------------------------------------------
# DataPipeline — integration tests
# ---------------------------------------------------------------------------


class TestDataPipeline:

    def _make_pipeline(self, symbol: str = "AAPL", price: float = 182.5):
        tick = MarketTick(
            symbol=symbol,
            price=price,
            volume=1_000_000.0,
            timestamp=TS,
            source="fixture",
        )
        provider = MagicMock()
        provider.fetch.return_value = tick

        normalizer = MarketNormalizer(source="fixture")
        engineer = FeatureEngineer(window_size=1)
        bus = MagicMock()

        pipeline = DataPipeline(
            provider=provider,
            normalizer=normalizer,
            engineer=engineer,
            bus=bus,
        )
        return pipeline, provider, bus

    def test_run_returns_feature_vector_event(self) -> None:
        pipeline, _, _ = self._make_pipeline()
        event = pipeline.run("AAPL")
        assert isinstance(event, FeatureVectorEvent)

    def test_run_event_type(self) -> None:
        pipeline, _, _ = self._make_pipeline()
        event = pipeline.run("AAPL")
        assert event.event_type == "data.feature_vector"

    def test_run_event_symbol(self) -> None:
        pipeline, _, _ = self._make_pipeline()
        event = pipeline.run("AAPL")
        assert event.symbol == "AAPL"

    def test_run_publishes_to_bus(self) -> None:
        pipeline, _, bus = self._make_pipeline()
        event = pipeline.run("AAPL")
        bus.publish.assert_called_once_with(event)

    def test_run_calls_provider_fetch(self) -> None:
        pipeline, provider, _ = self._make_pipeline()
        pipeline.run("AAPL")
        provider.fetch.assert_called_once_with("AAPL")

    def test_run_event_has_all_features(self) -> None:
        pipeline, _, _ = self._make_pipeline()
        event = pipeline.run("AAPL")
        assert "price_latest" in event.features
        assert "high" in event.features
        assert "low" in event.features

    def test_run_empty_symbol_raises(self) -> None:
        pipeline, _, _ = self._make_pipeline()
        with pytest.raises(ValueError):
            pipeline.run("")

    def test_run_source_quality_in_range(self) -> None:
        pipeline, _, _ = self._make_pipeline()
        event = pipeline.run("AAPL")
        assert 0.0 <= event.source_quality <= 1.0

    def test_run_event_timestamp_is_utc_aware(self) -> None:
        pipeline, _, _ = self._make_pipeline()
        event = pipeline.run("AAPL")
        assert event.timestamp.tzinfo is not None
