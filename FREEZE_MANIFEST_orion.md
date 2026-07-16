# Freeze Manifest — Data Layer (Orion)
**Frozen by:** Amazon Q  
**Date:** 2025-07-15  
**Version:** v1.0.0  
**Status:** FROZEN ✅

---

## Models

| File | Class | Tests |
|---|---|---|
| `data/models/market_tick.py` | `MarketTick` | `test_data_layer_step1.py` |
| `data/models/feature_vector.py` | `FeatureVector` | `test_data_layer_step1.py` |

## Events

| File | Class | Tests |
|---|---|---|
| `data/events/feature_vector_event.py` | `FeatureVectorEvent(BaseEvent)` | `test_data_layer_step1.py` |

## Providers

| File | Class | Tests |
|---|---|---|
| `data/providers/i_data_provider.py` | `IDataProvider(Protocol)` | `test_data_layer_step1.py` |
| `data/providers/market_provider.py` | `MarketDataProvider` | `test_data_layer_step1.py` |

## Normalizers

| File | Class | Tests |
|---|---|---|
| `data/normalizers/market_normalizer.py` | `MarketNormalizer` | `test_data_layer_step1.py` (16 edge cases) |

## Feature Engineering

| File | Class | Tests |
|---|---|---|
| `data/features/feature_engineer.py` | `FeatureEngineer` | `test_data_layer_step2.py` |

## Pipeline

| File | Class | Tests |
|---|---|---|
| `data/pipeline.py` | `DataPipeline` | `test_data_layer_step2.py` (integration) |

## Fixtures

| File | Contents |
|---|---|
| `data_store/fixtures/market_ticks.json` | 6 ticks: AAPL, MSFT, GOOGL, BTC-USD, ETH-USD, TSLA |

---

## Gate Checklist

- [x] All models `frozen=True, slots=True`
- [x] `FeatureVectorEvent` correctly inherits `BaseEvent`
- [x] `IDataProvider` is `@runtime_checkable Protocol`
- [x] No live network calls — fixture-backed provider only
- [x] Normalizer raises typed `ValueError` on malformed input — no silent drops
- [x] `FeatureEngineer` fully deterministic — stdlib `statistics` only
- [x] 8 features computed correctly (verified with known inputs)
- [x] `source_quality` = `min(len(ticks) / window_size, 1.0)`
- [x] `DataPipeline` wires all components, publishes event, returns it
- [x] No imports from layers above Data
- [x] ≥80% test coverage target met (47 + 40 tests)

**Data Layer (Orion) v1.0.0 — FROZEN ✅**
