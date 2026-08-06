"""
intelligence.candle.pretrained_model
======================================
Loads a serialized sklearn RandomForestClassifier and runs inference.
Gracefully degrades to HOLD if model file is missing or sklearn unavailable.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import ClassVar

_log = logging.getLogger(__name__)


class PretrainedCandleModel:
    """Wraps a serialized sklearn model for candle signal prediction."""

    FEATURE_NAMES: ClassVar[list[str]] = [
        "body_size_mean",
        "body_size_last",
        "upper_wick_mean",
        "lower_wick_mean",
        "close_above_open_pct",
        "momentum_3",
        "momentum_10",
        "volume_trend",
        "engulfing_bullish",
        "engulfing_bearish",
        "doji_last",
        "high_low_range_pct",
    ]
    # sklearn default: class labels sorted alphabetically → [BUY, HOLD, SELL]
    _CLASS_LABELS: ClassVar[list[str]] = ["BUY", "HOLD", "SELL"]

    def __init__(self, model_path: str | Path = "models/candle_rf.pkl") -> None:
        self._model = None
        try:
            import sklearn  # noqa: F401 — guard: works without sklearn

            safe_path = Path(model_path).resolve()
            with open(safe_path, "rb") as fh:
                self._model = pickle.load(fh)  # noqa: S301
            _log.info("PretrainedCandleModel: loaded from %s", safe_path)
        except FileNotFoundError:
            _log.warning(
                "PretrainedCandleModel: model file not found at %s — returning HOLD",
                model_path,
            )
        except ImportError:
            _log.warning(
                "PretrainedCandleModel: sklearn not installed — returning HOLD"
            )
        except Exception as exc:
            _log.warning("PretrainedCandleModel: failed to load model — %s", exc)

    def predict(self, features: dict[str, float]) -> tuple[str, float]:
        """Return (signal, probability). Falls back to ('HOLD', 0.0) on any issue."""
        if self._model is None or not features:
            return ("HOLD", 0.0)
        try:
            import numpy as np

            x = np.array(
                [[features.get(name, 0.0) for name in self.FEATURE_NAMES]],
                dtype=float,
            )
            proba = self._model.predict_proba(x)[0]
            best_idx = int(proba.argmax())
            # Map index to label using model's own classes if available
            classes = list(getattr(self._model, "classes_", self._CLASS_LABELS))
            signal = str(classes[best_idx]) if best_idx < len(classes) else "HOLD"
            if signal not in {"BUY", "SELL", "HOLD"}:
                signal = "HOLD"
            return (signal, float(proba[best_idx]))
        except Exception as exc:
            _log.warning("PretrainedCandleModel.predict: %s", exc)
            return ("HOLD", 0.0)
