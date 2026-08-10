"""
intelligence.candle.candle_strategy
======================================
Orchestrator: CandleFetcher → candle_features → PretrainedCandleModel
→ OllamaClient reviewer → Decision.

strategy_id = "candle-cil-v1"
Never raises — every failure path returns a HOLD Decision.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from intelligence.agent.ollama_client import OllamaClient
from intelligence.candle.candle_features import extract as extract_candle_features
from intelligence.candle.candle_fetcher import CandleFetcher
from intelligence.candle.pretrained_model import PretrainedCandleModel
from intelligence.models.decision import Decision

_log = logging.getLogger(__name__)

_STRATEGY_ID = "candle-cil-v1"
_HOLD = lambda sym, reason: Decision(
    symbol=sym,
    action="HOLD",
    confidence=0.0,
    rationale=reason,
    strategy_id=_STRATEGY_ID,
)


class CandleStrategy:
    """Candle Intelligence Layer — standalone orchestrator (not an IStrategy)."""

    def __init__(
        self,
        ollama_host: str = "http://localhost:11434",
        ollama_model: str = "llama3.1:8b",
        ollama_timeout: float = 30.0,
        model_path: str | Path = "models/candle_rf.pkl",
        interval: str = "5m",
        n_candles: int = 50,
        ttl_seconds: float = 600.0,
        min_model_confidence: float = 0.55,
    ) -> None:
        self._min_conf = min_model_confidence
        self._fetcher = CandleFetcher(
            interval=interval, n_candles=n_candles, ttl_seconds=ttl_seconds
        )
        self._model = PretrainedCandleModel(model_path=model_path)
        self._ollama = OllamaClient(
            model=ollama_model,
            host=ollama_host,
            timeout_seconds=ollama_timeout,
            temperature=0.1,
        )

    def evaluate(self, symbol: str) -> Decision:
        """Full pipeline: fetch → features → model → Ollama → Decision.

        Returns HOLD at every failure point. Never raises.
        """
        try:
            candles = self._fetcher.fetch(symbol)
            features = extract_candle_features(candles)
            signal, prob = self._model.predict(features)

            if prob < self._min_conf:
                return _HOLD(
                    symbol,
                    f"Model confidence {prob:.2f} below threshold {self._min_conf}",
                )

            # Build Ollama reviewer prompt
            prompt = self._build_prompt(symbol, signal, prob, features)

            try:
                raw = self._ollama.complete(prompt)
                action, confidence, rationale = self._parse_ollama(raw, signal, prob)
            except Exception as ollama_exc:
                _log.warning(
                    "CandleStrategy: Ollama unavailable (%s) — using model signal",
                    ollama_exc,
                )
                # Fallback: use pretrained model signal directly
                return Decision(
                    symbol=symbol,
                    action=signal,  # type: ignore[arg-type]
                    confidence=prob,
                    rationale=f"Pretrained model: {signal} ({prob:.0%}) — Ollama unavailable",
                    strategy_id=_STRATEGY_ID,
                )

            return Decision(
                symbol=symbol,
                action=action,  # type: ignore[arg-type]
                confidence=confidence,
                rationale=rationale[:500],
                strategy_id=_STRATEGY_ID,
            )

        except Exception as exc:
            _log.warning(
                "CandleStrategy.evaluate(%s): unexpected error — %s", symbol, exc
            )
            return _HOLD(symbol, f"Unexpected error: {exc}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self, symbol: str, signal: str, prob: float, features: dict[str, float]
    ) -> str:
        f = features
        return (
            "You are reviewing a pretrained ML model's trading signal.\n\n"
            f"Symbol: {symbol}\n"
            "Candle interval: 5m, last 50 candles\n\n"
            f"Pretrained model signal: {signal} (confidence: {prob:.0%})\n\n"
            "Candle summary:\n"
            f"- Momentum (3-candle): {f.get('momentum_3', 0):+.2f}%\n"
            f"- Momentum (10-candle): {f.get('momentum_10', 0):+.2f}%\n"
            f"- Bullish candles: {f.get('close_above_open_pct', 0):.0%} of last 50\n"
            f"- Last candle body: {f.get('body_size_last', 0):.3f}\n"
            f"- Volume trend: {f.get('volume_trend', 1):.2f}x recent vs baseline\n"
            f"- Engulfing bullish: {int(f.get('engulfing_bullish', 0))}\n"
            f"- Engulfing bearish: {int(f.get('engulfing_bearish', 0))}\n"
            f"- Doji (indecision): {int(f.get('doji_last', 0))}\n\n"
            "Your job: Review the model's signal. You may CONFIRM, OVERRIDE, or ABSTAIN.\n"
            "- CONFIRM: you agree with the model signal\n"
            "- OVERRIDE: you disagree — state your action instead\n"
            "- ABSTAIN: insufficient evidence — output HOLD\n\n"
            "Respond with ONLY this JSON:\n"
            '{"action": "BUY"|"SELL"|"HOLD", "confidence": 0.0-1.0, "rationale": "1 sentence"}'
        )

    def _parse_ollama(
        self, raw: str, model_signal: str, model_prob: float
    ) -> tuple[str, float, str]:
        """Parse Ollama JSON response. Returns (action, confidence, rationale).

        Fusion rules:
        - Ollama agrees  → use Ollama confidence
        - Ollama overrides → use Ollama action, cap confidence at 0.70
        - Ollama abstains (HOLD) → HOLD
        - Parse failure → HOLD
        """
        try:
            # Extract JSON from response (Ollama may wrap it in text)
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON object found in response")
            data = json.loads(raw[start:end])

            action = str(data.get("action", "HOLD")).upper()
            confidence = float(data.get("confidence", 0.0))
            rationale = str(data.get("rationale", "Ollama review"))

            if action not in {"BUY", "SELL", "HOLD"}:
                action = "HOLD"
            confidence = max(0.0, min(1.0, confidence))

            if action == "HOLD":
                return ("HOLD", 0.0, rationale)

            if action == model_signal:
                # Confirm — trust Ollama's calibration
                return (action, confidence, f"Confirmed: {rationale}")
            else:
                # Override — apply penalty cap
                return (action, min(confidence, 0.70), f"Override: {rationale}")

        except Exception as exc:
            _log.warning("CandleStrategy._parse_ollama: %s — falling back to HOLD", exc)
            return ("HOLD", 0.0, f"JSON parse failed: {exc}")
