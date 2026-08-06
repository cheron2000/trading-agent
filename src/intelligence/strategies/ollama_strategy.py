"""
intelligence.strategies.ollama_strategy
======================================

OllamaStrategy — Local LLM-powered trading strategy using Ollama.

Uses a local model to generate trading decisions based on
engineered market features. Provides AI reasoning in decision rationale.

Features:
  - JSON-mode enforced responses via the `format` parameter
  - Graceful fallback to HOLD on errors
  - Temperature 0.2 for consistent decisions
  - Full feature context in prompts

Python Version: 3.11+
"""

from __future__ import annotations

import json
import logging
from typing import ClassVar, Literal

from data.models.feature_vector import FeatureVector
from intelligence.agent.ollama_client import OllamaClient
from intelligence.models.decision import Decision
from intelligence.strategies.i_strategy import IStrategy

_log = logging.getLogger(__name__)


class OllamaStrategy:
    """Local LLM-powered trading strategy implementing IStrategy.

    Uses engineered features to prompt a local LLM for trading decisions.
    Always returns valid Decision objects, falling back to HOLD on errors.

    Usage::

        strategy = OllamaStrategy(model="llama3.1:8b")
        decision = strategy.evaluate(feature_vector)
    """

    STRATEGY_ID_PREFIX: ClassVar[str] = "ollama"
    DEFAULT_MODEL: ClassVar[str] = "llama3.1:8b"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        host: str = "http://localhost:11434",
        timeout: float = 30.0,
        temperature: float = 0.2,
    ) -> None:
        """
        Args:
            model:       Model alias (e.g., llama3.1:8b).
            host:        Base URL of the Ollama server.
            timeout:     Request timeout in seconds.
            temperature: Sampling temperature (0.0-1.0). Lower = more consistent.
        """
        self._client = OllamaClient(
            model=model,
            host=host,
            timeout_seconds=timeout,
            temperature=temperature,
        )
        self._model = model
        _log.info(
            "OllamaStrategy initialized — model: %s, host: %s",
            model, host
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

            # Strip markdown code blocks if present (safety net)
            response = response.strip()
            if response.startswith("```"):
                # Remove opening ```json or ``` line
                lines = response.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                response = "\n".join(lines).strip()

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

    def evaluate_with_context(
        self,
        feature_vector: FeatureVector,
        position_context: dict | None = None,
    ) -> Decision:
        """Evaluate a feature vector with optional position context.

        Args:
            feature_vector: Engineered features.
            position_context: Optional dict with keys:
                - 'has_position': bool
                - 'entry_price': float
                - 'current_price': float  
                - 'pnl_pct': float (e.g. 2.5 means +2.5%)
                - 'hold_cycles': int (how many cycles held)

        Returns:
            Decision with LLM-generated action and rationale.
        """
        if feature_vector is None:
            raise ValueError("feature_vector must not be None.")

        prompt = self._build_prompt(feature_vector, position_context=position_context)

        try:
            response = self._client.complete(prompt)
            _log.debug("LLM response for %s: %s", feature_vector.symbol, response[:100])

            # Strip markdown code blocks if present (safety net)
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                response = "\n".join(lines).strip()

            data = json.loads(response)
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

    def _build_prompt(self, fv: FeatureVector, position_context: dict | None = None) -> str:
        """Build a rich trading prompt from feature vector with technical indicators.

        Args:
            fv: FeatureVector with engineered features including RSI, MACD, Bollinger Bands.

        Returns:
            Formatted prompt string for the LLM with specific trading rules.
        """
        f = fv.features

        # Core price data
        price = f.get("price_latest", f.get("price", 0.0))
        price_change_pct = f.get("price_change_pct", 0.0)
        volume_ratio = f.get("volume_ratio", 1.0)
        high = f.get("high", price)
        low = f.get("low", price)

        # Trend indicators
        sma_5 = f.get("sma_5", price)
        sma_20 = f.get("sma_20", price)
        trend = "UPTREND" if sma_5 > sma_20 else "DOWNTREND"

        # RSI
        rsi = f.get("rsi", 50.0)
        if rsi < 30:
            rsi_signal = "OVERSOLD (strong buy candidate)"
        elif rsi < 40:
            rsi_signal = "MILDLY OVERSOLD (weak buy)"
        elif rsi > 70:
            rsi_signal = "OVERBOUGHT (strong sell candidate)"
        elif rsi > 60:
            rsi_signal = "MILDLY OVERBOUGHT (weak sell)"
        else:
            rsi_signal = "NEUTRAL"

        # MACD
        macd_line = f.get("macd_line", 0.0)
        _macd_signal = f.get("macd_signal", 0.0)  # Reserved for future use
        macd_hist = f.get("macd_histogram", 0.0)
        if macd_hist > 0 and macd_line > 0:
            macd_signal_txt = "BULLISH (MACD above signal, positive territory)"
        elif macd_hist > 0 and macd_line < 0:
            macd_signal_txt = "BULLISH CROSSOVER (recovering from negative)"
        elif macd_hist < 0 and macd_line < 0:
            macd_signal_txt = "BEARISH (MACD below signal, negative territory)"
        else:
            macd_signal_txt = "BEARISH CROSSOVER (losing momentum)"

        # Bollinger Bands
        bb_pos = f.get("bb_position", 0.5)
        bb_lower = f.get("bb_lower", price * 0.98)
        bb_upper = f.get("bb_upper", price * 1.02)
        if bb_pos < 0.2:
            bb_signal = f"NEAR LOWER BAND (potential bounce, support at ${bb_lower:.2f})"
        elif bb_pos > 0.8:
            bb_signal = f"NEAR UPPER BAND (potential reversal, resistance at ${bb_upper:.2f})"
        else:
            bb_signal = f"MID-BAND (position: {bb_pos:.0%} of range)"

        # Volume
        if volume_ratio > 1.5:
            vol_signal = f"{volume_ratio:.1f}x average (HIGH - confirms moves)"
        elif volume_ratio < 0.7:
            vol_signal = f"{volume_ratio:.1f}x average (LOW - weak conviction)"
        else:
            vol_signal = f"{volume_ratio:.1f}x average (NORMAL)"

        # Count bullish vs bearish signals
        bullish = sum([
            rsi < 40,
            macd_hist > 0,
            bb_pos < 0.3,
            sma_5 > sma_20,
            price_change_pct > 0,
            volume_ratio > 1.2,
        ])
        bearish = sum([
            rsi > 60,
            macd_hist < 0,
            bb_pos > 0.7,
            sma_5 < sma_20,
            price_change_pct < 0,
            volume_ratio > 1.5 and price_change_pct < 0,
        ])

        # Build position context section
        if position_context and position_context.get("has_position"):
            entry = position_context.get("entry_price", 0.0)
            pnl_pct = position_context.get("pnl_pct", 0.0)
            hold_cycles = position_context.get("hold_cycles", 0)
            pnl_emoji = "📈" if pnl_pct >= 0 else "📉"
            position_section = f"""
== CURRENT POSITION ==
Status:         HOLDING {fv.symbol}
Entry price:    ${entry:.2f}
Current P&L:    {pnl_emoji} {pnl_pct:+.2f}%
Held for:       {hold_cycles} cycle(s)
Note: You already OWN this asset. Consider taking profit or cutting loss.
Position Management Rule: When has_position is true and pnl_pct > 5%, suggest taking profit. When pnl_pct < -3%, suggest cutting the loss.
"""
        else:
            position_section = """
== CURRENT POSITION ==
Status:         NO POSITION (flat)
Note: You do NOT own this asset. A BUY would open a new position.
"""

        # News context
        news_ctx = ""
        if position_context and position_context.get("news_context"):
            news_ctx = f"""
== NEWS SENTIMENT ==
{position_context['news_context']}
Use this news to adjust confidence. Bullish news + bullish technicals = higher confidence.
Bearish news contradicting bullish technicals = lower confidence / HOLD.
"""

        prompt = f"""You are a disciplined quantitative momentum trader analyzing {fv.symbol}.
You follow strict signal-based rules and never deviate from them.

== MARKET DATA ==
Price:          ${price:.2f} ({price_change_pct:+.2f}% change)
Range:          ${low:.2f} - ${high:.2f}
Trend (SMA):    SMA5=${sma_5:.2f} vs SMA20=${sma_20:.2f} → {trend}
{position_section}
== TECHNICAL SIGNALS ==
RSI ({rsi:.1f}):      {rsi_signal}
MACD:           {macd_signal_txt} (histogram: {macd_hist:+.4f})
Boll. Bands:    {bb_signal}
Volume:         {vol_signal}
{news_ctx}
== SIGNAL SUMMARY ==
Bullish signals: {bullish}/6
Bearish signals: {bearish}/6

== YOUR TRADING RULES ==
1. STRONG BUY: bullish >= 5 → confidence 0.85-0.95, full position
2. BUY: bullish >= 3 AND RSI < 65 → confidence 0.60-0.80
3. HOLD: bullish 2, bearish 2 (truly mixed) → confidence 0.50
4. SELL: bearish >= 3 AND RSI > 35 → confidence 0.60-0.80  
5. STRONG SELL: bearish >= 5 → confidence 0.85-0.95
6. Override: RSI < 25 → always BUY (oversold). RSI > 75 → always SELL (overbought).
7. Volume confirmation: if volume_ratio > 1.5, boost confidence by 0.10

== REQUIRED JSON RESPONSE ==
Respond with ONLY this JSON object, no other text:
{{"action": "BUY" or "SELL" or "HOLD", "confidence": 0.0-1.0, "rationale": "1-2 sentence explanation citing specific indicators"}}"""

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
assert isinstance(OllamaStrategy(), IStrategy), (
    "OllamaStrategy does not satisfy the IStrategy Protocol."
)
