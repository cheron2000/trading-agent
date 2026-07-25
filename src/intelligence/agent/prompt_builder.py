"""
intelligence.agent.prompt_builder
=====================================

PromptBuilder — constructs structured prompts from a FeatureVector.

Produces a JSON-schema-constrained prompt that instructs the LLM to
return strictly structured output. Never constructs prompts from
unsanitized raw text to prevent prompt injection.

Python Version: 3.11+
"""

from __future__ import annotations

import json

from data.models.feature_vector import FeatureVector


class PromptBuilder:
    """Builds deterministic, injection-resistant prompts for the LLM agent.

    The output prompt instructs the LLM to respond with a JSON object
    matching exactly::

        {
            "action": "BUY" | "SELL" | "HOLD",
            "confidence": <float 0.0–1.0>,
            "rationale": "<string>"
        }

    All feature values are embedded as sanitized numeric strings —
    no free-form external text (e.g. news headlines) is included
    at this stage to prevent prompt injection.
    """

    SYSTEM_PROMPT: str = (
        "You are a quantitative trading assistant. "
        "Analyze the provided market features and respond with a JSON object only. "
        "Your response must be valid JSON with exactly these keys: "
        "\"action\" (one of: BUY, SELL, HOLD), "
        "\"confidence\" (float between 0.0 and 1.0), "
        "\"rationale\" (brief string explanation). "
        "Do not include any text outside the JSON object."
    )

    def build(self, feature_vector: FeatureVector, news_context: str = "") -> str:
        """Build a structured prompt from a FeatureVector.

        Args:
            feature_vector: Engineered features for a symbol.
            news_context:   Optional news sentiment string from AVNewsProvider.
                            Injected after features if provided.

        Returns:
            A complete prompt string ready to send to the LLM client.

        Raises:
            ValueError: If ``feature_vector`` is None.
        """
        if feature_vector is None:
            raise ValueError("feature_vector must not be None.")

        features_json = json.dumps(
            {k: round(v, 6) for k, v in sorted(feature_vector.features.items())},
            indent=2,
        )

        news_section = ""
        if news_context and news_context.strip():
            news_section = f"\n{news_context.strip()}\n"

        return (
            f"{self.SYSTEM_PROMPT}\n\n"
            f"Symbol: {feature_vector.symbol}\n"
            f"Timestamp: {feature_vector.timestamp.isoformat()}\n"
            f"Source quality: {feature_vector.source_quality:.4f}\n"
            f"Features:\n{features_json}\n"
            f"{news_section}\n"
            f"Respond with JSON only:"
        )
