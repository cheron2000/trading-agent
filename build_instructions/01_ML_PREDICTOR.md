# Task 1: ML Directional Predictor

## Goal
Build a lightweight ML model that predicts the probability of price moving UP
in the next trading interval. The output is a single float `P(up) ∈ [0.0, 1.0]`
that will be injected into the ATLAS LLM prompt as an independent quantitative signal.

---

## File to Create

**Path:** `src/intelligence/ml/directional_predictor.py`

Also create `src/intelligence/ml/__init__.py` (empty file).

---

## Class Specification

```python
class DirectionalPredictor:
    """
    Lightweight gradient boosting classifier that predicts the probability
    of price increasing in the next interval.
    
    Uses sklearn's GradientBoostingClassifier (already in requirements.txt
    as scikit-learn>=1.3.0). Do NOT add xgboost or lightgbm as dependencies.
    
    Training data:
      - Computed on-the-fly from the last N price observations (default N=100)
      - Features: RSI, MACD histogram, Bollinger %b, ATR ratio, volume ratio,
                  price change over last 5 bars, price change over last 10 bars
      - Label: 1 if price[i+1] > price[i], else 0
    
    Caching:
      - Model is retrained only once per symbol per 30 minutes (TTL cache).
      - Between retrains, predict() returns cached model output.
    """
```

### Constructor

```python
def __init__(self, lookback: int = 100, retrain_ttl_seconds: float = 1800.0) -> None:
```

- `lookback`: Number of historical price points to train on (default 100)
- `retrain_ttl_seconds`: Seconds before model is retrained (default 1800 = 30 min)
- Internal state:
  - `self._models: dict[str, GradientBoostingClassifier]` — per-symbol trained models
  - `self._last_trained: dict[str, float]` — monotonic timestamp of last training per symbol
  - `self._cache: dict[str, float]` — cached prediction per symbol

### Method: `predict(symbol: str, prices: list[float], volumes: list[float]) -> float`

**Returns:** `P(price_up_next_interval)` as a float from 0.0 to 1.0.

**Algorithm:**

1. Check if a model exists for this symbol AND `time.monotonic() - self._last_trained[symbol] < retrain_ttl_seconds`.
   - If yes: compute features from the LAST data point only and return `model.predict_proba()`.
   - If no: retrain (step 2).

2. **Feature Engineering for ML (from raw prices and volumes):**
   Compute the following for EACH data point `i` (where `i >= 14` to have enough lookback):
   
   ```
   feature_0: RSI(14) at point i               — use the _compute_rsi static method logic from FeatureEngineer
   feature_1: MACD histogram at point i         — (EMA12 - EMA26) - signal
   feature_2: Bollinger %b at point i           — (price - bb_lower) / (bb_upper - bb_lower)
   feature_3: ATR ratio at point i              — ATR(5) / ATR(20)
   feature_4: Volume ratio at point i           — volume[i] / mean(volumes[i-20:i])
   feature_5: Price change % over last 5 bars   — (price[i] - price[i-5]) / price[i-5] * 100
   feature_6: Price change % over last 10 bars  — (price[i] - price[i-10]) / price[i-10] * 100
   ```

   **Label:** `1 if prices[i+1] > prices[i] else 0`
   
   This means you can only create training samples for indices `i` from `max(14, 20)` to `len(prices) - 2`
   (need at least 20 lookback for volume ratio, and need `i+1` to exist for the label).

3. **Training:**
   ```python
   from sklearn.ensemble import GradientBoostingClassifier
   
   model = GradientBoostingClassifier(
       n_estimators=50,
       max_depth=3,
       learning_rate=0.1,
       random_state=42,
   )
   model.fit(X_train, y_train)
   ```

4. **Prediction:**
   Compute the same 7 features for the LAST data point (index `-1`), then:
   ```python
   prob = model.predict_proba(X_latest.reshape(1, -1))[0][1]  # P(class=1) = P(up)
   ```

5. **Edge Cases:**
   - If `len(prices) < lookback` or `len(prices) < 25`: return `0.5` (no signal — neutral).
   - If training data has < 10 samples: return `0.5`.
   - If model training raises any exception: return `0.5` and log warning.
   - Always clamp output to `[0.0, 1.0]`.

---

## Helper Functions to Reuse

You should replicate (NOT import) these computation patterns from `src/data/features/feature_engineer.py`:

- **RSI calculation:** See `FeatureEngineer._compute_rsi()` at line 249
- **EMA calculation:** See `FeatureEngineer._ema()` at line 263
- **ATR calculation:** See `FeatureEngineer._compute_atr()` at line 236

Do NOT import from `feature_engineer.py` — the ML module should be self-contained
with its own copies of these computations to avoid circular dependencies.

---

## Test File to Create

**Path:** `src/tests/test_directional_predictor.py`

Write at least 4 tests:

1. **test_predict_neutral_with_insufficient_data**: Pass < 25 prices, assert returns 0.5
2. **test_predict_returns_valid_probability**: Pass 100+ synthetic prices (e.g., `[100 + i*0.1 + random.uniform(-0.5, 0.5) for i in range(150)]`), assert output is in `[0.0, 1.0]`
3. **test_predict_caching_ttl**: Call predict twice with same data quickly, verify second call is fast (model not retrained)
4. **test_predict_with_trending_data**: Pass clearly uptrending data (`[100 + i for i in range(150)]`), assert P(up) > 0.5

Import path: `from intelligence.ml.directional_predictor import DirectionalPredictor`

---

## Important Constraints

- Use ONLY `sklearn.ensemble.GradientBoostingClassifier` — do NOT use xgboost, lightgbm, or tensorflow
- Use ONLY stdlib + numpy (comes with sklearn) for feature computations
- The class must be stateless across symbols — each symbol gets its own independent model
- Thread safety is NOT required (called from single main thread in run_hour.py)
- Keep logging to `logging.getLogger(__name__)` with WARNING level for errors only
