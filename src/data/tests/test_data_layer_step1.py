"""
Data Layer (Orion) — Step 1 tests.
Covers: MarketTick, FeatureVector, FeatureVectorEvent,
        MarketDataProvider (fixture contract), MarketNormalizer.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from data.events.feature_vector_event import FeatureVectorEvent
from data.models.feature_vector import FeatureVector
from data.models.market_tick import MarketTick
from data.normalizers.market_normalizer import MarketNormalizer
from data.providers.i_data_provider import IDataProvider
from data.providers.market_provider import MarketDataProvider

TS = datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc)

FIXTURE_DATA = [
    {
        "symbol": "AAPL",
        "price": 182.50,
        "volume": 1200000.0,
        "timestamp": "2024-01-15T14:30:00+00:00",
        "source": "fixture",
    },
    {
        "symbol": "MSFT",
        "price": 374.25,
        "volume": 850000.0,
        "timestamp": "2024-01-15T14:30:00+00:00",
        "source": "fixture",
    },
    {
        "symbol": "BTC-USD",
        "price": 42500.0,
        "volume": 18500.5,
        "timestamp": "2024-01-15T14:30:00+00:00",
        "source": "fixture",
    },
]


# ---------------------------------------------------------------------------
# Fixture helper
# ---------------------------------------------------------------------------


@pytest.fixture()
def fixture_file(tmp_path: Path) -> Path:
    f = tmp_path / "market_ticks.json"
    f.write_text(json.dumps(FIXTURE_DATA), encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# MarketTick
# ---------------------------------------------------------------------------


class TestMarketTick:

    def test_valid_creation(self) -> None:
        t = MarketTick(
            symbol="AAPL", price=182.5, volume=1_000.0, timestamp=TS, source="fixture"
        )
        assert t.symbol == "AAPL"
        assert t.price == 182.5

    def test_empty_symbol_raises(self) -> None:
        with pytest.raises(ValueError):
            MarketTick(symbol="", price=1.0, volume=0.0, timestamp=TS, source="x")

    def test_zero_price_raises(self) -> None:
        with pytest.raises(ValueError):
            MarketTick(symbol="AAPL", price=0.0, volume=0.0, timestamp=TS, source="x")

    def test_negative_price_raises(self) -> None:
        with pytest.raises(ValueError):
            MarketTick(symbol="AAPL", price=-1.0, volume=0.0, timestamp=TS, source="x")

    def test_negative_volume_raises(self) -> None:
        with pytest.raises(ValueError):
            MarketTick(symbol="AAPL", price=1.0, volume=-1.0, timestamp=TS, source="x")

    def test_zero_volume_allowed(self) -> None:
        t = MarketTick(symbol="AAPL", price=1.0, volume=0.0, timestamp=TS, source="x")
        assert t.volume == 0.0

    def test_empty_source_raises(self) -> None:
        with pytest.raises(ValueError):
            MarketTick(symbol="AAPL", price=1.0, volume=0.0, timestamp=TS, source="")

    def test_immutability(self) -> None:
        t = MarketTick(symbol="AAPL", price=1.0, volume=0.0, timestamp=TS, source="x")
        with pytest.raises((AttributeError, TypeError)):
            t.price = 2.0  # type: ignore

    def test_timestamp_utc_property(self) -> None:
        naive_ts = datetime(2024, 1, 1, 12, 0, 0)
        t = MarketTick(
            symbol="AAPL", price=1.0, volume=0.0, timestamp=naive_ts, source="x"
        )
        assert t.timestamp_utc.tzinfo is not None

    def test_to_dict(self) -> None:
        t = MarketTick(
            symbol="AAPL", price=182.5, volume=1000.0, timestamp=TS, source="fixture"
        )
        d = t.to_dict()
        assert d["symbol"] == "AAPL"
        assert d["price"] == 182.5
        assert "timestamp" in d


# ---------------------------------------------------------------------------
# FeatureVector
# ---------------------------------------------------------------------------


class TestFeatureVector:

    def test_valid_creation(self) -> None:
        fv = FeatureVector(
            symbol="AAPL", timestamp=TS, features={"sma_20": 180.0}, source_quality=0.9
        )
        assert fv.symbol == "AAPL"
        assert fv.feature_count == 1

    def test_empty_symbol_raises(self) -> None:
        with pytest.raises(ValueError):
            FeatureVector(symbol="", timestamp=TS, features={}, source_quality=0.5)

    def test_source_quality_above_1_raises(self) -> None:
        with pytest.raises(ValueError):
            FeatureVector(symbol="AAPL", timestamp=TS, features={}, source_quality=1.1)

    def test_source_quality_below_0_raises(self) -> None:
        with pytest.raises(ValueError):
            FeatureVector(symbol="AAPL", timestamp=TS, features={}, source_quality=-0.1)

    def test_source_quality_boundary_values(self) -> None:
        FeatureVector(symbol="AAPL", timestamp=TS, features={}, source_quality=0.0)
        FeatureVector(symbol="AAPL", timestamp=TS, features={}, source_quality=1.0)

    def test_features_not_dict_raises(self) -> None:
        with pytest.raises(TypeError):
            FeatureVector(symbol="AAPL", timestamp=TS, features="bad", source_quality=0.5)  # type: ignore

    def test_immutability(self) -> None:
        fv = FeatureVector(symbol="AAPL", timestamp=TS, features={}, source_quality=0.5)
        with pytest.raises((AttributeError, TypeError)):
            fv.symbol = "MSFT"  # type: ignore

    def test_to_dict(self) -> None:
        fv = FeatureVector(
            symbol="AAPL", timestamp=TS, features={"rsi": 55.0}, source_quality=0.8
        )
        d = fv.to_dict()
        assert d["symbol"] == "AAPL"
        assert d["features"] == {"rsi": 55.0}


# ---------------------------------------------------------------------------
# FeatureVectorEvent
# ---------------------------------------------------------------------------


class TestFeatureVectorEvent:

    def test_valid_creation(self) -> None:
        e = FeatureVectorEvent(
            event_type="data.feature_vector",
            symbol="AAPL",
            timestamp=TS,
            features={"sma_20": 180.0},
            source_quality=0.9,
        )
        assert e.event_type == "data.feature_vector"
        assert e.symbol == "AAPL"
        assert e.event_id is not None

    def test_inherits_base_event_fields(self) -> None:
        e = FeatureVectorEvent(
            event_type="data.feature_vector",
            symbol="AAPL",
            timestamp=TS,
            features={},
            source_quality=1.0,
        )
        assert hasattr(e, "event_id")
        assert hasattr(e, "occurred_at")
        assert hasattr(e, "schema_version")

    def test_empty_symbol_raises(self) -> None:
        with pytest.raises(ValueError):
            FeatureVectorEvent(
                event_type="data.feature_vector",
                symbol="",
                timestamp=TS,
                features={},
                source_quality=1.0,
            )

    def test_none_timestamp_raises(self) -> None:
        with pytest.raises(ValueError):
            FeatureVectorEvent(
                event_type="data.feature_vector",
                symbol="AAPL",
                timestamp=None,  # type: ignore
                features={},
                source_quality=1.0,
            )

    def test_none_features_raises(self) -> None:
        with pytest.raises(ValueError):
            FeatureVectorEvent(
                event_type="data.feature_vector",
                symbol="AAPL",
                timestamp=TS,
                features=None,  # type: ignore
                source_quality=1.0,
            )

    def test_invalid_source_quality_raises(self) -> None:
        with pytest.raises(ValueError):
            FeatureVectorEvent(
                event_type="data.feature_vector",
                symbol="AAPL",
                timestamp=TS,
                features={},
                source_quality=1.5,
            )

    def test_to_dict_contains_all_fields(self) -> None:
        e = FeatureVectorEvent(
            event_type="data.feature_vector",
            symbol="AAPL",
            timestamp=TS,
            features={"rsi": 60.0},
            source_quality=0.95,
        )
        d = e.to_dict()
        assert d["symbol"] == "AAPL"
        assert d["features"] == {"rsi": 60.0}
        assert d["source_quality"] == 0.95
        assert "event_id" in d
        assert "event_type" in d


# ---------------------------------------------------------------------------
# MarketDataProvider — fixture contract tests
# ---------------------------------------------------------------------------


class TestMarketDataProvider:

    def test_satisfies_idataprovider_protocol(self, fixture_file: Path) -> None:
        provider = MarketDataProvider(fixture_path=fixture_file)
        assert isinstance(provider, IDataProvider)

    def test_source_name(self, fixture_file: Path) -> None:
        provider = MarketDataProvider(fixture_path=fixture_file)
        assert provider.source_name == "fixture"

    def test_fetch_known_symbol(self, fixture_file: Path) -> None:
        provider = MarketDataProvider(fixture_path=fixture_file)
        tick = provider.fetch("AAPL")
        assert tick.symbol == "AAPL"
        assert tick.price == 182.50
        assert tick.volume == 1_200_000.0
        assert tick.source == "fixture"

    def test_fetch_case_insensitive(self, fixture_file: Path) -> None:
        provider = MarketDataProvider(fixture_path=fixture_file)
        tick = provider.fetch("aapl")
        assert tick.symbol == "AAPL"

    def test_fetch_all_fixture_symbols(self, fixture_file: Path) -> None:
        provider = MarketDataProvider(fixture_path=fixture_file)
        for item in FIXTURE_DATA:
            tick = provider.fetch(item["symbol"])
            assert tick.price == item["price"]

    def test_fetch_unknown_symbol_raises(self, fixture_file: Path) -> None:
        provider = MarketDataProvider(fixture_path=fixture_file)
        with pytest.raises(ValueError):
            provider.fetch("UNKNOWN")

    def test_fetch_empty_symbol_raises(self, fixture_file: Path) -> None:
        provider = MarketDataProvider(fixture_path=fixture_file)
        with pytest.raises(ValueError):
            provider.fetch("")

    def test_missing_fixture_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            MarketDataProvider(fixture_path=tmp_path / "nonexistent.json")

    def test_tick_timestamp_is_utc_aware(self, fixture_file: Path) -> None:
        provider = MarketDataProvider(fixture_path=fixture_file)
        tick = provider.fetch("AAPL")
        assert tick.timestamp.tzinfo is not None


# ---------------------------------------------------------------------------
# MarketNormalizer
# ---------------------------------------------------------------------------


class TestMarketNormalizer:

    def test_valid_normalization(self) -> None:
        n = MarketNormalizer(source="alpaca")
        raw = {
            "symbol": "AAPL",
            "price": 182.5,
            "volume": 1000.0,
            "timestamp": "2024-01-15T14:30:00+00:00",
        }
        tick = n.normalize(raw)
        assert tick.symbol == "AAPL"
        assert tick.price == 182.5
        assert tick.source == "alpaca"

    def test_symbol_uppercased(self) -> None:
        n = MarketNormalizer(source="x")
        tick = n.normalize(
            {
                "symbol": "aapl",
                "price": 1.0,
                "volume": 0.0,
                "timestamp": "2024-01-15T14:30:00+00:00",
            }
        )
        assert tick.symbol == "AAPL"

    def test_non_dict_raises_type_error(self) -> None:
        n = MarketNormalizer(source="x")
        with pytest.raises(TypeError):
            n.normalize("not a dict")  # type: ignore

    def test_missing_symbol_raises(self) -> None:
        n = MarketNormalizer(source="x")
        with pytest.raises(ValueError, match="symbol"):
            n.normalize(
                {"price": 1.0, "volume": 0.0, "timestamp": "2024-01-15T14:30:00+00:00"}
            )

    def test_empty_symbol_raises(self) -> None:
        n = MarketNormalizer(source="x")
        with pytest.raises(ValueError):
            n.normalize(
                {
                    "symbol": "",
                    "price": 1.0,
                    "volume": 0.0,
                    "timestamp": "2024-01-15T14:30:00+00:00",
                }
            )

    def test_missing_price_raises(self) -> None:
        n = MarketNormalizer(source="x")
        with pytest.raises(ValueError, match="price"):
            n.normalize(
                {
                    "symbol": "AAPL",
                    "volume": 0.0,
                    "timestamp": "2024-01-15T14:30:00+00:00",
                }
            )

    def test_zero_price_raises(self) -> None:
        n = MarketNormalizer(source="x")
        with pytest.raises(ValueError):
            n.normalize(
                {
                    "symbol": "AAPL",
                    "price": 0,
                    "volume": 0.0,
                    "timestamp": "2024-01-15T14:30:00+00:00",
                }
            )

    def test_negative_price_raises(self) -> None:
        n = MarketNormalizer(source="x")
        with pytest.raises(ValueError):
            n.normalize(
                {
                    "symbol": "AAPL",
                    "price": -5.0,
                    "volume": 0.0,
                    "timestamp": "2024-01-15T14:30:00+00:00",
                }
            )

    def test_non_numeric_price_raises(self) -> None:
        n = MarketNormalizer(source="x")
        with pytest.raises(ValueError):
            n.normalize(
                {
                    "symbol": "AAPL",
                    "price": "bad",
                    "volume": 0.0,
                    "timestamp": "2024-01-15T14:30:00+00:00",
                }
            )

    def test_missing_volume_raises(self) -> None:
        n = MarketNormalizer(source="x")
        with pytest.raises(ValueError, match="volume"):
            n.normalize(
                {
                    "symbol": "AAPL",
                    "price": 1.0,
                    "timestamp": "2024-01-15T14:30:00+00:00",
                }
            )

    def test_negative_volume_raises(self) -> None:
        n = MarketNormalizer(source="x")
        with pytest.raises(ValueError):
            n.normalize(
                {
                    "symbol": "AAPL",
                    "price": 1.0,
                    "volume": -1.0,
                    "timestamp": "2024-01-15T14:30:00+00:00",
                }
            )

    def test_missing_timestamp_raises(self) -> None:
        n = MarketNormalizer(source="x")
        with pytest.raises(ValueError, match="timestamp"):
            n.normalize({"symbol": "AAPL", "price": 1.0, "volume": 0.0})

    def test_invalid_timestamp_string_raises(self) -> None:
        n = MarketNormalizer(source="x")
        with pytest.raises(ValueError):
            n.normalize(
                {
                    "symbol": "AAPL",
                    "price": 1.0,
                    "volume": 0.0,
                    "timestamp": "not-a-date",
                }
            )

    def test_datetime_object_accepted(self) -> None:
        n = MarketNormalizer(source="x")
        tick = n.normalize(
            {"symbol": "AAPL", "price": 1.0, "volume": 0.0, "timestamp": TS}
        )
        assert tick.timestamp == TS

    def test_naive_timestamp_gets_utc(self) -> None:
        n = MarketNormalizer(source="x")
        tick = n.normalize(
            {
                "symbol": "AAPL",
                "price": 1.0,
                "volume": 0.0,
                "timestamp": "2024-01-15T14:30:00",
            }
        )
        assert tick.timestamp.tzinfo is not None

    def test_empty_source_raises(self) -> None:
        with pytest.raises(ValueError):
            MarketNormalizer(source="")
