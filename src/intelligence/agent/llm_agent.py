"""
intelligence.agent.llm_agent
==============================

LLMAgent — evaluates a FeatureVector via an injected LLM client.

The LLM client is always injected — no live API calls are made here.
In production a real client adapter is injected; in tests a mock is used.

JSON parsing is strict: any deviation from the expected schema raises
ValueError immediately — never silently falls back to a default action.

Python Version: 3.11+
"""

from __future__ import annotations

import json
from typing import Any, ClassVar, Protocol, runtime_checkable

from data.models.feature_vector import FeatureVector
from intelligence.agent.prompt_builder import PromptBuilder
from intelligence.models.decision import Decision


@runtime_checkable
class ILLMClient(Protocol):
    """Minimal protocol for an LLM completion client."""

    def complete(self, prompt: str) -> str:
        """Send a prompt and return the model's text response."""
        ...


class LLMAgent:
    """Trading decision agent backed by an injected LLM client.

    Implements the same evaluate() interface as IStrategy so it can
    be used interchangeably in the pipeline.

    Parses the LLM response as strict JSON::

        {"action": "BUY"|"SELL"|"HOLD", "confidence": float, "rationale": str}

    Any parsing failure or schema violation raises ValueError immediately.
    """

    _VALID_ACTIONS: ClassVar[frozenset[str]] = frozenset({"BUY", "SELL", "HOLD"})

    def __init__(
        self,
        llm_client: Any,
        prompt_builder: PromptBuilder,
        strategy_id: str = "llm-agent",
    ) -> None:
        """
        Args:
            llm_client:     Any object with a ``complete(prompt: str) -> str`` method.
            prompt_builder: PromptBuilder instance for constructing prompts.
            strategy_id:    Identifier stamped on produced Decisions.

        Raises:
            ValueError: If ``strategy_id`` is empty.
        """
        if not strategy_id or not strategy_id.strip():
            raise ValueError("strategy_id must not be empty.")
        self._client = llm_client
        self._prompt_builder = prompt_builder
        self._strategy_id = strategy_id.strip()

    # ------------------------------------------------------------------
    # IStrategy-compatible interface
    # ------------------------------------------------------------------

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    def evaluate(self, feature_vector: FeatureVector) -> Decision:
        """Evaluate a feature vector via the LLM and return a Decision.

        Args:
            feature_vector: Engineered features for a symbol.

        Returns:
            Immutable ``Decision`` parsed from the LLM JSON response.

        Raises:
            ValueError: If the LLM response is not valid JSON, missing
                        required keys, has an invalid action, or has a
                        confidence score outside [0.0, 1.0].
        """
        if feature_vector is None:
            raise ValueError("feature_vector must not be None.")

        prompt = self._prompt_builder.build(feature_vector)
        raw_response = self._client.complete(prompt)
        return self._parse_response(raw_response, feature_vector.symbol)

    # ------------------------------------------------------------------
    # Strict JSON parsing
    # ------------------------------------------------------------------

    def _parse_response(self, raw: str, symbol: str) -> Decision:
        """Parse and validate the LLM JSON response.

        Args:
            raw:    Raw string response from the LLM client.
            symbol: Symbol to stamp on the resulting Decision.

        Returns:
            Validated ``Decision``.

        Raises:
            ValueError: On any schema or value violation.
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM response is not valid JSON: {raw!r}") from exc

        if not isinstance(data, dict):
            raise TypeError(
                f"LLM response must be a JSON object, got: {type(data).__name__}."
            )

        # Validate action
        action = data.get("action")
        if action not in self._VALID_ACTIONS:
            raise ValueError(
                f"LLM response 'action' must be one of "
                f"{sorted(self._VALID_ACTIONS)}, got: {action!r}."
            )

        # Validate confidence
        try:
            confidence = float(data["confidence"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "LLM response 'confidence' must be a numeric value."
            ) from exc

        if not (0.0 <= confidence <= 1.0):
            raise ValueError(
                f"LLM response 'confidence' must be in [0.0, 1.0], "
                f"got: {confidence}."
            )

        # Validate rationale
        rationale = data.get("rationale", "")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("LLM response 'rationale' must be a non-empty string.")

        return Decision(
            symbol=symbol,
            action=action,  # type: ignore[arg-type]
            confidence=confidence,
            rationale=rationale.strip(),
            strategy_id=self._strategy_id,
        )
