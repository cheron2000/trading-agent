"""
intelligence.strategies.atlas_strategy
==========================================

AtlasStrategy — Adaptive Tactical LLM Algorithmic System (ATLAS).

Implements the 6-step ATLAS trading strategy:
  Step 1: Circuit breaker check
  Step 2: Regime gating (Trending, Ranging, Volatile, Crisis)
  Step 3: 3-layer confluence scoring (Trend, Momentum, Volatility)
  Step 4: Context memory anti-drift & anti-flip-flop
  Step 5: Dynamic ATR risk parameters & 2:1 R:R gate
  Step 6: Quarter-Kelly confidence calibration (0-100)

Dual Engine Support:
  - Tries Groq LLM (Llama 3.3 70B) if API key is present.
  - Automatically falls back to local Ollama (Llama 3.1 8B) if Groq is unavailable.

Python Version: 3.11+
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.parse
from typing import ClassVar

from data.models.feature_vector import FeatureVector
from intelligence.models.decision import Decision

_log = logging.getLogger(__name__)


class AtlasStrategy:
    """ATLAS Strategy — Regime-Gated Multi-Factor Confluence Strategy with Dual LLM Backend."""

    STRATEGY_ID: ClassVar[str] = "ATLAS-LLM"

    def __init__(
        self,
        groq_api_key: str | list[str] | None = None,
        groq_model: str = "llama-3.3-70b-versatile",
        ollama_host: str = "http://localhost:11434",
        ollama_model: str = "llama3.1:8b",
        timeout: float = 30.0,
    ) -> None:
        """
        Args:
            groq_api_key: Optional Groq API key(s).
            groq_model: Groq model name (default: llama-3.3-70b-versatile).
            ollama_host: Ollama server URL.
            ollama_model: Ollama model name (default: llama3.1:8b).
            timeout: HTTP request timeout in seconds.
        """
        self._groq_keys = (
            [groq_api_key]
            if isinstance(groq_api_key, str)
            else groq_api_key if isinstance(groq_api_key, list) else []
        )
        self._groq_keys = [k.strip() for k in self._groq_keys if k and k.strip()]
        self._groq_key_idx = 0
        self._groq_model = groq_model

        self._ollama_host = ollama_host.rstrip("/")
        self._ollama_model = ollama_model
        self._timeout = timeout

    @property
    def strategy_id(self) -> str:
        return self.STRATEGY_ID

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

        response_json_str = None
        engine_used = None

        # 1. Try Groq if keys are configured
        if self._groq_keys:
            try:
                response_json_str = self._call_groq(prompt)
                engine_used = f"Groq ({self._groq_model})"
            except Exception as exc:
                _log.warning(
                    "ATLAS Groq call failed (%s) — falling back to local Ollama", exc
                )

        # 2. Fall back to local Ollama
        if response_json_str is None:
            try:
                response_json_str = self._call_ollama(prompt)
                engine_used = f"Ollama ({self._ollama_model})"
            except Exception as exc:
                _log.warning(
                    "ATLAS Ollama call failed (%s) — returning default HOLD", exc
                )
                return Decision(
                    symbol=feature_vector.symbol,
                    action="HOLD",
                    confidence=0.0,
                    rationale=f"ATLAS LLM connection error: {str(exc)[:100]}",
                    strategy_id=self.strategy_id,
                )

        # 3. Parse and validate JSON output
        return self._parse_atlas_response(
            feature_vector.symbol, response_json_str, engine_used
        )

    # ------------------------------------------------------------------
    # LLM Engines (Groq & Ollama)
    # ------------------------------------------------------------------

    def _call_groq(self, prompt: str) -> str:
        """Call Groq API with key rotation."""
        api_key = self._groq_keys[self._groq_key_idx]
        self._groq_key_idx = (self._groq_key_idx + 1) % len(self._groq_keys)

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._groq_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]

    def _call_ollama(self, prompt: str) -> str:
        """Call local Ollama server."""
        url = f"{self._ollama_host}/api/generate"
        payload = {
            "model": self._ollama_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["response"]

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
        daily_trend = pos_ctx.get("daily_trend", "NEUTRAL") if pos_ctx else "NEUTRAL"
        trade_reflections = pos_ctx.get("trade_reflections", "") if pos_ctx else ""

        pos_str = f"Status: {'HOLDING' if has_pos else 'FLAT (No Position)'}, Entry: ${entry_price:.2f}, PnL: {pnl_pct:+.2f}%, Held: {hold_cycles} cycles"

        # Build optional sections
        reflections_section = ""
        if trade_reflections:
            reflections_section = f"""
{trade_reflections}
"""

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
Detected Regime: {regime_label.upper()}           Regime Confidence: {regime_confidence:.0%}

Position Context: {pos_str}
News Context: {news_ctx[:400]}
{reflections_section}
═══════════════════════════════════════
DECISION PROCESS — follow in order:
═══════════════════════════════════════
STEP 1 — Confirm Regime Gate:
  - trending (ADX > 25) -> Trend-following (ride direction with VWAP/MACD confirm)
  - ranging  (ADX < 20) -> Mean-reversion (fade toward VWAP from Bollinger extremes)
  - volatile (ATR ratio >= 1.5) -> Breakout continuation only (cap max confidence at 70)
  - crisis   (ATR ratio >= 2.5) -> Capital preservation only (HOLD / flat)
  IMPORTANT: If daily trend is UPTREND/DOWNTREND, weight it heavily. BUY in UPTREND regime
  is safer than in NEUTRAL. SELL in DOWNTREND is higher-conviction.

STEP 2 — Score Confluence (3 layers):
  a) Trend layer: MACD line/signal/histogram agree with direction?
  b) Momentum layer: RSI supports the trade? (30-60 for BUY pullback, 40-70 for SELL rally)
  c) Volatility layer: Price position in Bollinger Bands supports direction?
  Scoring:
    3/3 agree = Strong signal → confidence 75-95
    2/3 agree = Marginal but actionable → confidence 60-74
    0-1/3 agree = No signal → HOLD
  RSI OVERRIDE: RSI < 25 → always BUY (extreme oversold). RSI > 75 → always SELL (extreme overbought).

STEP 3 — Risk & Reward Gate:
  - Stop-loss: 1.5-2x ATR from price.
  - Take-profit: minimum 2:1 reward:risk ratio. If < 1.5:1 → HOLD.

STEP 4 — Assign Calibrated Confidence (0-100):
  - 0-49  : Weak or no signal → HOLD
  - 50-59 : Marginal, not enough conviction → HOLD
  - 60-74 : 2/3 layers agree in trending/ranging regime → BUY/SELL
  - 75-89 : 3/3 layers agree → STRONG BUY/SELL
  - 90-100: 3/3 agree + RSI override or extreme condition → HIGHEST CONVICTION

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
        self, symbol: str, text: str, engine_name: str | None
    ) -> Decision:
        try:
            raw = text.strip()
            # Extract JSON object between first '{' and last '}'
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
                conf_norm = 0.01  # 1 out of 100 for HOLD
            else:
                conf_norm = max(0.0, min(1.0, conf_raw))

            # Enforce ATLAS Step 4 rule: confidence < 0.60 must be HOLD
            if conf_norm < 0.60:
                action = "HOLD"

            reasoning = data.get("reasoning", "ATLAS evaluation")
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
