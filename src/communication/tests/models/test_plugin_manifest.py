"""
Unit tests for communication.models.plugin_manifest.
"""

from __future__ import annotations

import pytest

from communication.models import PluginManifest

VALID_KWARGS = dict(
    plugin_id="plugin-001",
    name="MarketDataPlugin",
    version="1.0.0",
    description="Provides market data.",
    author="AITOS Team",
    api_version="1.0.0",
    entry_point="plugins.market_data.MarketDataPlugin",
)


class TestPluginManifest:

    def test_valid_minimal_creation(self) -> None:
        m = PluginManifest(**VALID_KWARGS)
        assert m.plugin_id == "plugin-001"
        assert m.dependencies == ()
        assert m.capabilities == ()
        assert m.configuration_schema is None

    def test_valid_full_creation(self) -> None:
        m = PluginManifest(
            **VALID_KWARGS,
            dependencies=("dep-a",),
            optional_dependencies=("dep-b",),
            capabilities=("stream",),
            event_subscriptions=("market.tick",),
            event_publications=("feature.vector",),
            tags=("data",),
            configuration_schema="schema-v1",
        )
        assert m.has_dependencies is True
        assert m.publishes_events is True
        assert m.subscribes_to_events is True

    @pytest.mark.parametrize(
        "field",
        ["plugin_id", "name", "version", "author", "api_version", "entry_point"],
    )
    def test_empty_required_field_raises(self, field: str) -> None:
        kwargs = {**VALID_KWARGS, field: ""}
        with pytest.raises(ValueError):
            PluginManifest(**kwargs)

    def test_empty_description_raises(self) -> None:
        with pytest.raises(ValueError):
            PluginManifest(**{**VALID_KWARGS, "description": ""})

    def test_description_too_long_raises(self) -> None:
        with pytest.raises(ValueError):
            PluginManifest(**{**VALID_KWARGS, "description": "x" * 2049})

    def test_duplicate_dependencies_raises(self) -> None:
        with pytest.raises(ValueError):
            PluginManifest(**VALID_KWARGS, dependencies=("dep-a", "dep-a"))

    def test_empty_dependency_value_raises(self) -> None:
        with pytest.raises(ValueError):
            PluginManifest(**VALID_KWARGS, dependencies=("",))

    def test_duplicate_capabilities_raises(self) -> None:
        with pytest.raises(ValueError):
            PluginManifest(**VALID_KWARGS, capabilities=("stream", "stream"))

    def test_duplicate_event_subscriptions_raises(self) -> None:
        with pytest.raises(ValueError):
            PluginManifest(**VALID_KWARGS, event_subscriptions=("a.b", "a.b"))

    def test_duplicate_event_publications_raises(self) -> None:
        with pytest.raises(ValueError):
            PluginManifest(**VALID_KWARGS, event_publications=("a.b", "a.b"))

    def test_empty_configuration_schema_raises(self) -> None:
        with pytest.raises(ValueError):
            PluginManifest(**VALID_KWARGS, configuration_schema="")

    def test_has_dependencies_false(self) -> None:
        m = PluginManifest(**VALID_KWARGS)
        assert m.has_dependencies is False

    def test_publishes_events_false(self) -> None:
        m = PluginManifest(**VALID_KWARGS)
        assert m.publishes_events is False

    def test_subscribes_to_events_false(self) -> None:
        m = PluginManifest(**VALID_KWARGS)
        assert m.subscribes_to_events is False

    def test_immutability(self) -> None:
        m = PluginManifest(**VALID_KWARGS)
        with pytest.raises((AttributeError, TypeError)):
            m.name = "other"  # type: ignore[misc]

    def test_to_dict(self) -> None:
        m = PluginManifest(**VALID_KWARGS)
        d = m.to_dict()
        assert d["plugin_id"] == "plugin-001"
        assert d["dependencies"] == []
        assert d["configuration_schema"] is None

    def test_str_representation(self) -> None:
        m = PluginManifest(**VALID_KWARGS)
        assert "plugin-001" in str(m)
        assert "MarketDataPlugin" in str(m)
