"""
data.pipeline
==============

DataPipeline — end-to-end Data Layer orchestrator.

Connects provider → normalizer → feature engineer → EventBus into
a single entry point. Publishes a FeatureVectorEvent and returns it.

Design constraints:
- No imports from layers above Data.
- All dependencies injected via constructor (mockable in tests).

Python Version: 3.11+
"""

from __future__ import annotations

from datetime import datetime, timezone

from communication.interfaces.i_event_bus import IEventBus
from data.events.feature_vector_event import FeatureVectorEvent
from data.features.feature_engineer import FeatureEngineer
from data.normalizers.market_normalizer import MarketNormalizer
from data.providers.i_data_provider import IDataProvider


class DataPipeline:
    """Orchestrates the full Data Layer processing pipeline.

    Flow:
        1. ``provider.fetch(symbol)``       → ``MarketTick``
        2. ``normalizer.normalize(tick_dict)`` → validated ``MarketTick``
        3. ``engineer.compute([tick])``     → ``FeatureVector``
        4. Wrap in ``FeatureVectorEvent``
        5. ``bus.publish(event)``
        6. Return event

    All dependencies are injected — the pipeline has no concrete
    provider, normalizer, or bus references of its own.
    """

    def __init__(
        self,
        provider: IDataProvider,
        normalizer: MarketNormalizer,
        engineer: FeatureEngineer,
        bus: IEventBus,
    ) -> None:
        """
        Args:
            provider:   Data source adapter implementing IDataProvider.
            normalizer: MarketNormalizer for payload validation.
            engineer:   FeatureEngineer for feature computation.
            bus:        EventBus to publish the FeatureVectorEvent on.
        """
        self._provider = provider
        self._normalizer = normalizer
        self._engineer = engineer
        self._bus = bus

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, symbol: str) -> FeatureVectorEvent:
        """Execute the full pipeline for a symbol.

        Args:
            symbol: Canonical ticker symbol (e.g. ``"AAPL"``).

        Returns:
            The published ``FeatureVectorEvent``.

        Raises:
            ValueError:   If ``symbol`` is empty or not found.
            RuntimeError: If the provider is unavailable.
        """
        if not symbol or not symbol.strip():
            raise ValueError("symbol must not be empty.")

        # Step 1 — fetch from provider (already a MarketTick)
        tick = self._provider.fetch(symbol)

        # Step 2 — re-validate via normalizer (catches any drift)
        validated_tick = self._normalizer.normalize(tick.to_dict())

        # Step 3 — compute features
        feature_vector = self._engineer.compute([validated_tick])

        # Step 4 — wrap in event
        ts = feature_vector.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        event = FeatureVectorEvent(
            event_type="data.feature_vector",
            symbol=feature_vector.symbol,
            timestamp=ts,
            features=dict(feature_vector.features),
            source_quality=feature_vector.source_quality,
        )

        # Step 5 — publish
        self._bus.publish(event)

        # Step 6 — return
        return event
