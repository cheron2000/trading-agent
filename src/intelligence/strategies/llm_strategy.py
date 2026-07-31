"""
intelligence.strategies.llm_strategy
======================================

LLMStrategy — Groq LLM-powered trading strategy.

Uses Groq's Llama 3.1 8B model to generate trading decisions based on
engineered market features. Provides AI reasoning in decision rationale.

Features:
  - JSON-mode enforced responses
  - Graceful fallback to HOLD on errors
  - Temperature 0.1 for consistent decisions
  - Full feature context in prompts

Python Version: 3.11+
"""

from __future__ import annotations

import json
import logging
from typing import ClassVar, Literal

from data.models.feature_vector import FeatureVector
from intelligence.agent.groq_client import GroqClient
from intelligence.models.decision import Decision
from intelligence.strategies.i_strategy import IStrategy

_log = logging.getLogger(__name__)


class LLMStrategy:
    """Groq LLM-powered trading strategy implementing IStrategy.

    Uses engineered features to prompt an LLM for trading decisions.
    Always returns valid Decision objects, falling back to HOLD on errors.

    Usage::

        # Single key (backward compatible)
        strategy = LLMStrategy(api_key="your_groq_key")
        
        # Multiple keys (auto-rotation on rate limits)
        strategy = LLMStrategy(api_key=["key1", "key2", "key3"])
        
        decision = strategy.evaluate(feature_vector)
    """

    STRATEGY_ID_PREFIX: ClassVar[str] = "groq-llm"
    DEFAULT_MODEL: ClassVar[str] = "llama3-8b"

    def __init__(
        self,
        api_key: str | list[str],
        model: str = DEFAULT_MODEL,
        temperature: float = 0.1,
    ) -> None:
        """
        Args:
            api_key:     Groq API key(s). Pass a single string or list of strings.
                         When multiple keys provided, rotates on 429 rate limit.
            model:       Model alias (llama3-8b, llama3-70b, mixtral).
            temperature: Sampling temperature (0.0-1.0). Lower = more consistent.

        Raises:
            ValueError: If api_key is empty or contains no valid keys.
        """
        # Normalize to list for validation
        if isinstance(api_key, str):
            keys = [api_key.strip()]
        else:
            keys = [k.strip() for k in api_key if k and k.strip()]
        
        if not keys:
            raise ValueError("api_key must not be empty.")

        self._client = GroqClient(
            api_key=api_key,  # Pass original format (str or list)
            model=model,
            temperature=temperature,
            max_tokens=256,
            timeout=10.0,
        )
        self._model = model
        key_count = len(keys)
        _log.info(
            "LLMStrategy initialized — model: %s, keys: %d",
            model, key_count
        )

    # ------------------------------------------------------------------
    # IStrategy implementation
    # ------------------------------------------------------------------

    @property
    def strategy_id(self) -> str:
        """Return the unique strategy identifier."""
        return f"{self.STRATEGY_ID_PREFIX}-{self._model}"

    def evaluate(self, feature_vector: FeatureVector) -> Decision:
        """Evaluate a feature vector using the LLM.

        Args:
            feature_vector: Engineered features. Must contain price-related data.

        Returns:
            Immutable Decision with LLM-generated action and rationale.

        Raises:
            ValueError: If feature_vector is None.
        """
        if feature_vector is None:
            raise ValueError("feature_vector must not be None.")

        # Build prompt with market context
        prompt = self._build_prompt(feature_vector)

        try:
            # Call LLM
            response = self._client.complete(prompt)
            _log.debug("LLM response for %s: %s", feature_vector.symbol, response[:100])

            # Parse JSON response
            data = json.loads(response)

            # Validate and extract fields
            action = self._validate_action(data.get("action", "HOLD"))
            confidence = self._validate_confidence(data.get("confidence", 0.5))
            rationale = self._validate_rationale(data.get("rationale", "LLM decision"))

            return Decision(
                symbol=feature_vector.symbol,
                action=action,
                confidence=confidence,
                rationale=rationale,
                strategy_id=self.strategy_id,
            )

        except Exception as exc:
            # Graceful fallback to HOLD on any error
            _log.warning(
                "LLM strategy error for %s: %s — falling back to HOLD",
                feature_vector.symbol, exc
            )
            return Decision(
                symbol=feature_vector.symbol,
                action="HOLD",
                confidence=0.0,
                rationale=f"LLM error: {str(exc)[:100]}",
                strategy_id=self.strategy_id,
            )

    # ------------------------------------------------------------------
    # Prompt engineering
    # ------------------------------------------------------------------

    def _build_prompt(self, fv: FeatureVector) -> str:
        """Build a trading prompt from feature vector.

        Args:
            fv: FeatureVector with engineered features.

        Returns:
            Formatted prompt string for the LLM.
        """
        features = fv.features

        # Extract key features (with defaults)
        price = features.get("price", 0.0)
        price_change_pct = features.get("price_change_pct", 0.0)
        volume = features.get("volume", 0.0)
        volatility = features.get("volatility", 0.0)
        sma_5 = features.get("sma_5", price)
        sma_20 = features.get("sma_20", price)

        # Build structured prompt
        prompt = f"""You are a professional quantitative trader analyzing {fv.symbol}.

**Current Market Data:**
- Price: ${price:.2f}
- Price Change: {price_change_pct:+.2f}%
- Volume: {volume:,.0f}
- Volatility: {volatility:.4f}
- SMA(5): ${sma_5:.2f}
- SMA(20): ${sma_20:.2f}

**Your Task:**
Analyze the data and decide whether to BUY, SELL, or HOLD.

**Rules:**
1. BUY when you see strong bullish signals (positive momentum, high volume, uptrend)
2. SELL when you see strong bearish signals (negative momentum, breakdown, weakness)
3. HOLD when signals are mixed or insufficient
4. Confidence should reflect your conviction (0.0 = no conviction, 1.0 = very high)

**Response Format (JSON only):**
{{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "rationale": "Brief explanation of your reasoning (1-2 sentences)"
}}

Respond with ONLY the JSON object. No markdown, no explanations."""

        return prompt

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_action(self, action: str) -> Literal["BUY", "SELL", "HOLD"]:
        """Validate and normalize action string.

        Args:
            action: Action string from LLM response.

        Returns:
            Validated action literal.
        """
        action_upper = str(action).strip().upper()
        if action_upper in ("BUY", "SELL", "HOLD"):
            return action_upper  # type: ignore
        _log.warning("Invalid action from LLM: %s — defaulting to HOLD", action)
        return "HOLD"

    def _validate_confidence(self, confidence: float | str) -> float:
        """Validate and clamp confidence score.

        Args:
            confidence: Confidence value from LLM response.

        Returns:
            Clamped confidence in [0.0, 1.0].
        """
        try:
            conf = float(confidence)
            return max(0.0, min(1.0, conf))
        except (ValueError, TypeError):
            _log.warning("Invalid confidence from LLM: %s — defaulting to 0.5", confidence)
            return 0.5

    def _validate_rationale(self, rationale: str) -> str:
        """Validate and truncate rationale string.

        Args:
            rationale: Rationale string from LLM response.

        Returns:
            Validated rationale (max 2048 chars).
        """
        if not rationale or not str(rationale).strip():
            return "LLM provided no rationale"
        
        rat = str(rationale).strip()
        if len(rat) > 2048:
            return rat[:2045] + "..."
        return rat


# Runtime protocol check
assert isinstance(LLMStrategy(api_key="dummy_key_for_check"), IStrategy), (
    "LLMStrategy does not satisfy the IStrategy Protocol."
)
