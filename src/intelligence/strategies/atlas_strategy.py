"""
intelligence.strategies.atlas_strategy
==========================================

AtlasStrategy — Adaptive Tactical LLM Algorithmic System (ATLAS).

Implements the 6-step ATLAS trading strategy with sequential multi-key Groq LLM rotation:
  Step 1: Circuit breaker check
  Step 2: Regime gating (Trending, Ranging, Volatile, Crisis)
  Step 3: 3-layer confluence scoring (Trend, Momentum, Volatility)
  Step 4: Context memory anti-drift & anti-flip-flop
  Step 5: Dynamic ATR risk parameters & 2:1 R:R gate
  Step 6: Quarter-Kelly confidence calibration (0-100)

Features:
  - Sequential key rolling across all configured Groq API keys.
  - Automatic failover to next key if any key encounters a rate limit or HTTP error.
  - Exposes active key metadata for live web dashboard streaming.

Python Version: 3.11+
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import ClassVar

from data.models.feature_vector import FeatureVector
from intelligence.models.decision import Decision

_log = logging.getLogger(__name__)


class AtlasStrategy:
    """ATLAS Strategy — Regime-Gated Multi-Factor Confluence Strategy with Multi-Key Groq LLM Backend."""

    STRATEGY_ID: ClassVar[str] = "ATLAS-LLM"

    def __init__(
        self,
        groq_api_key: str | list[str] | None = None,
        groq_model: str = "llama-3.1-8b-instant",
        timeout: float = 30.0,
    ) -> None:
        """
        Args:
            groq_api_key: Mandatory Groq API key or list of keys.
            groq_model: Groq model name (default: llama-3.1-8b-instant).
            timeout: HTTP request timeout in seconds.
        """
        keys_input = (
            [groq_api_key]
            if isinstance(groq_api_key, str)
            else groq_api_key if isinstance(groq_api_key, list) else []
        )
        self._groq_keys = [k.strip() for k in keys_input if k and k.strip()]
        if not self._groq_keys:
            raise ValueError("AtlasStrategy requires at least one valid Groq API key.")

        self._groq_key_idx = 0
        self._groq_model = groq_model
        self._timeout = timeout
        self._last_key_info = ""

    @property
    def strategy_id(self) -> str:
        return self.STRATEGY_ID

    @property
    def last_key_info(self) -> str:
        """Returns metadata for the most recently used Groq key."""
        return self._last_key_info

    def get_current_key_status(self) -> dict:
        """Returns key status dictionary for web dashboard streaming."""
        total = len(self._groq_keys)
        curr_idx = (self._groq_key_idx - 1) % total if total > 0 else 0
        curr_key = self._groq_keys[curr_idx] if total > 0 else ""
        masked = f"{curr_key[:8]}...{curr_key[-4:]}" if len(curr_key) > 12 else curr_key
        return {
            "total_keys": total,
            "current_index": curr_idx + 1,
            "masked_key": masked,
            "last_info": self._last_key_info,
            "model": self._groq_model,
        }

    def evaluate(self, feature_vector: FeatureVector) -> Decision:
        return self.evaluate_with_context(feature_vector, position_context=None)

    def evaluate_with_context(
        self,
        feature_vector: FeatureVector,
        position_context: dict | None = None,
    ) -> Decision:
        """Evaluate market features using the 6-step ATLAS system prompt."""
        if feature_vector is None:
            raise ValueError("feature_vector must not be None.")

        prompt = self._build_atlas_prompt(feature_vector, position_context)

        try:
            response_json_str, engine_used = self._call_groq(prompt)
        except Exception as exc:
            _log.error("ATLAS Groq LLM evaluation failed after rolling all keys: %s", exc)
            return Decision(
                symbol=feature_vector.symbol,
                action="HOLD",
                confidence=0.0,
                rationale=f"[Groq LLM Error] All Groq API keys failed: {str(exc)[:100]}",
                strategy_id=self.strategy_id,
            )

        # Parse and validate JSON output
        return self._parse_atlas_response(
            feature_vector, response_json_str, engine_used, position_context
        )

    # ------------------------------------------------------------------
    # Groq LLM Engine (Sequential Key Rotation & Auto-Failover)
    # ------------------------------------------------------------------

    def _call_groq(self, prompt: str) -> tuple[str, str]:
        """Call Groq API with sequential key rolling.
        
        Returns:
            Tuple of (response_json_str, engine_display_name).
        """
        attempts = 0
        max_attempts = len(self._groq_keys)
        last_error = None

        while attempts < max_attempts:
            key_index = self._groq_key_idx
            api_key = self._groq_keys[key_index]
            # Advance rotation index for next call
            self._groq_key_idx = (self._groq_key_idx + 1) % max_attempts

            masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else api_key
            key_tag = f"Key #{key_index + 1}/{max_attempts} ({masked_key})"
            self._last_key_info = key_tag

            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "python-httpx/0.27.0",
            }
            payload = {
                "model": self._groq_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            }

            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    content = data["choices"][0]["message"]["content"]
                    engine_display = f"Groq {self._groq_model} | {key_tag}"
                    _log.info("Groq call succeeded using %s", key_tag)
                    return content, engine_display
            except Exception as exc:
                last_error = exc
                attempts += 1
                _log.warning(
                    "Groq %s failed (%s) — auto-rolling to key #%d...",
                    key_tag,
                    exc,
                    (self._groq_key_idx + 1),
                )

        raise RuntimeError(f"All {max_attempts} Groq keys failed. Last error: {last_error}")

    # ------------------------------------------------------------------
    # System Prompt Generator
    # ------------------------------------------------------------------

    def _build_atlas_prompt(
        self,
        fv: FeatureVector,
        pos_ctx: dict | None = None,
    ) -> str:
        f = fv.features

        symbol = fv.symbol
        price = f.get("price_latest", f.get("price", 0.0))
        vwap = f.get("vwap", price)
        rsi = f.get("rsi", 50.0)
        macd_line = f.get("macd_line", 0.0)
        macd_signal = f.get("macd_signal", 0.0)
        macd_hist = f.get("macd_histogram", 0.0)
        bb_upper = f.get("bb_upper", price * 1.02)
        bb_mid = f.get("bb_middle", price)
        bb_lower = f.get("bb_lower", price * 0.98)
        bb_pos = f.get("bb_position", 0.5)
        atr = f.get("atr", price * 0.02)
        atr_ratio = f.get("atr_ratio", 1.0)
        regime_label = f.get("regime_label", "trending")
        regime_confidence = f.get("regime_confidence", 0.80)
        adx = f.get("adx", 0.0)

        # Position context
        has_pos = pos_ctx.get("has_position", False) if pos_ctx else False
        entry_price = pos_ctx.get("entry_price", 0.0) if pos_ctx else 0.0
        pnl_pct = pos_ctx.get("pnl_pct", 0.0) if pos_ctx else 0.0
        hold_cycles = pos_ctx.get("hold_cycles", 0) if pos_ctx else 0
        news_ctx = pos_ctx.get("news_context", "None") if pos_ctx else "None"
        news_score = pos_ctx.get("news_sentiment_score", 0.0) if pos_ctx else 0.0
        daily_trend = pos_ctx.get("daily_trend", "NEUTRAL") if pos_ctx else "NEUTRAL"
        trade_reflections = pos_ctx.get("trade_reflections", "") if pos_ctx else ""

        pos_str = f"Status: {'HOLDING' if has_pos else 'FLAT (No Position)'}, Entry: ${entry_price:.2f}, PnL: {pnl_pct:+.2f}%, Held: {hold_cycles} cycles"

        reflections_section = ""
        if trade_reflections:
            reflections_section = f"\n{trade_reflections}\n"

        return f"""You are the decision core of ATLAS (Adaptive Tactical LLM Algorithmic System).
You do not predict prices. You classify setups and state your genuine confidence (0-100)
so a downstream Quarter-Kelly sizing layer can size the trade correctly.
Calibration honesty is your most important property — a correct "I'm not sure" is more valuable than a confident guess.

═══════════════════════════════════════
CURRENT STATE (Ground Truth Injected Values)
═══════════════════════════════════════
Asset: {symbol}                         Price: ${price:.2f}
VWAP: ${vwap:.2f}                        RSI(14): {rsi:.1f}
MACD: line={macd_line:+.4f} signal={macd_signal:+.4f} hist={macd_hist:+.4f}
Bollinger Bands: upper=${bb_upper:.2f} mid=${bb_mid:.2f} lower=${bb_lower:.2f} (percent_b={bb_pos:.2f})
ATR(14): ${atr:.4f}                       ATR ratio: {atr_ratio:.2f}
ADX(14): {adx:.1f}                         Daily Trend: {daily_trend}
Detected Regime: {str(regime_label).upper()}           Regime Confidence: {regime_confidence:.0%}

Position Context: {pos_str}
News Sentiment Score: {news_score:+.2f} (-1.0 to +1.0)
News Context: {news_ctx[:400]}
{reflections_section}
═══════════════════════════════════════
═══════════════════════════════════════
DECISION PROCESS — follow in order:
═══════════════════════════════════════
STEP 1 — Confirm Regime Gate:
  - trending (ADX > 25) -> Trend-following (ride direction with VWAP/MACD confirm)
  - ranging  (ADX < 20) -> Mean-reversion (require strict lower/upper band and RSI boundary setup)
  - volatile (ATR ratio >= 1.5) -> High volatility — require 3/3 layer confluence (cap max confidence at 70)
  - crisis   (ATR ratio >= 2.5) -> Capital preservation only (HOLD / stay flat)

STEP 2 — Score Confluence (3 layers):
  a) Trend layer: MACD line/signal/histogram agree with direction
  b) Momentum layer: RSI supports direction (BUY if RSI < 45; SELL if RSI > 55)
  c) Volatility layer: Price position in Bollinger Bands supports direction (percent_b < 0.35 for BUY, > 0.65 for SELL)
  Scoring:
    3/3 agree = High conviction signal → confidence 75-90
    2/3 agree = Actionable signal → confidence 60-74
    1/3 or 0/3 agree = Insufficient confluence → HOLD (confidence < 60)

STEP 3 — Risk & Reward Gate:
  - Stop-loss: 1.5-2x ATR from entry price.
  - Take-profit: Minimum 2:1 reward:risk ratio. If < 2:1 → HOLD.

STEP 4 — Defensive Confidence Calibration (0-100):
  - 0-59  : Insufficient setup / low conviction → HOLD
  - 60-74 : 2/3 layers agree → BUY / SELL
  - 75-100: 3/3 layers agree + favorable regime → HIGH CONVICTION BUY / SELL

═══════════════════════════════════════
REQUIRED JSON RESPONSE ONLY
═══════════════════════════════════════
Respond with ONLY this JSON object, no markdown or surrounding text:
{{
  "asset": "{symbol}",
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": <integer 0-100>,
  "regime_used": "{regime_label}",
  "confluence": {{
    "trend_layer": true | false,
    "momentum_layer": true | false,
    "volatility_layer": true | false,
    "agreement_count": <0-3>
  }},
  "risk": {{
    "stop_loss_price": <number or null>,
    "take_profit_price": <number or null>,
    "reward_risk_ratio": <number or null>
  }},
  "reasoning": "<2-3 sentences citing exact RSI, MACD, BB, ADX, and regime numbers>"
}}"""

    def _parse_atlas_response(
        self,
        fv: FeatureVector,
        text: str,
        engine_name: str | None,
        pos_ctx: dict | None = None,
    ) -> Decision:
        symbol = fv.symbol
        try:
            raw = text.strip()
            first_brace = raw.find("{")
            last_brace = raw.rfind("}")
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                raw = raw[first_brace : last_brace + 1]

            data = json.loads(raw)
            action = data.get("action", "HOLD").upper()
            if action not in ("BUY", "SELL", "HOLD"):
                action = "HOLD"

            conf_raw = float(data.get("confidence", 50))
            if conf_raw > 1.0:
                conf_norm = max(0.0, min(1.0, conf_raw / 100.0))
            elif conf_raw == 1.0 and action == "HOLD":
                conf_norm = 0.01
            else:
                conf_norm = max(0.0, min(1.0, conf_raw))

            # Defensive Gate: require confidence >= 0.60 for trades
            if conf_norm < 0.60:
                action = "HOLD"

            reasoning = data.get("reasoning", "ATLAS defensive evaluation")
            engine_display = engine_name or "UnknownEngine"
            rationale = f"[{engine_display}] [{data.get('regime_used', 'N/A').upper()}] {reasoning}"

            return Decision(
                symbol=symbol,
                action=action,
                confidence=conf_norm,
                rationale=rationale,
                strategy_id=self.STRATEGY_ID,
            )
        except Exception as exc:
            _log.warning("Failed to parse ATLAS JSON (%s): %s", exc, text[:100])
            return Decision(
                symbol=symbol,
                action="HOLD",
                confidence=0.0,
                rationale=f"ATLAS parse error: {str(exc)[:50]}",
                strategy_id=self.STRATEGY_ID,
            )
