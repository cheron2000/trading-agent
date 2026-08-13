# Task 3: Integration into ATLAS Prompt and run_hour.py

## Goal
Wire the ML Predictor (Task 1) and Support/Resistance Calculator (Task 2)
into the live trading loop and inject their outputs into the ATLAS LLM prompt.

---

## Overview of Changes

You will modify exactly 3 existing files and create 0 new files:

1. **`run_hour.py`** — Initialize the two new modules and pass their outputs into `pos_context`
2. **`src/intelligence/strategies/atlas_strategy.py`** — Read new context fields and format them into the prompt
3. **`requirements.txt`** — No changes needed (scikit-learn already listed)

---

## Step 1: Modify `run_hour.py`

### 1A. Add imports (near top of file, after existing imports around line 26)

Add these lines AFTER the existing `sys.path.insert(0, "src")` line:

```python
from intelligence.ml.directional_predictor import DirectionalPredictor
from data.features.support_resistance import SupportResistanceCalculator
```

### 1B. Initialize modules (in the initialization block, around lines 310-335)

Add these lines AFTER the existing `trade_memory` initialization:

```python
# ML Directional Predictor & Support/Resistance Calculator
ml_predictor = DirectionalPredictor(lookback=100, retrain_ttl_seconds=1800.0)
sr_calculator = SupportResistanceCalculator(swing_window=5, cache_ttl_seconds=900.0)
print("[OK] ML Directional Predictor and S/R Calculator initialized")
```

### 1C. Compute predictions per symbol (inside the `for symbol in symbols_this_cycle:` loop)

Find the section around line 614 where `ticks` are fetched:
```python
ticks = provider.fetch_recent(symbol, n=26)
fv = engineer.compute(ticks)
```

Add AFTER that block (before the ADX Regime Classification section):

```python
# Fetch extended history for ML predictor & S/R calculator
try:
    extended_ticks = provider.fetch_recent(symbol, n=100)
    extended_prices = [t.price for t in extended_ticks]
    extended_volumes = [t.volume for t in extended_ticks]
except Exception:
    extended_prices = [t.price for t in ticks]
    extended_volumes = [t.volume for t in ticks]

# ML directional prediction
ml_prob_up = ml_predictor.predict(symbol, extended_prices, extended_volumes)

# Support/Resistance levels
sr_levels = sr_calculator.calculate(symbol, extended_prices, tick.price)
```

### 1D. Pass results into `pos_context` dict

Find the `pos_context` dictionary construction (around line 648-664).
Add these 2 new keys INSIDE the dictionary:

```python
pos_context = {
    # ... existing keys ...
    "ml_prob_up": ml_prob_up,           # ADD THIS
    "sr_levels": sr_levels,             # ADD THIS
}
```

### 1E. Add a print line for ML prediction

After the existing `print(f"  [{symbol}] Daily trend: {daily_trend}")` line, add:

```python
print(f"  [{symbol}] ML P(up)={ml_prob_up:.2f} | S={sr_levels.get('nearest_support', 'N/A')} R={sr_levels.get('nearest_resistance', 'N/A')}")
```

---

## Step 2: Modify `src/intelligence/strategies/atlas_strategy.py`

### 2A. Read new context fields in `_build_atlas_prompt()`

Find the section where `pos_ctx` fields are read (around line 212-220).
Add after the existing `trade_reflections` line:

```python
ml_prob_up = pos_ctx.get("ml_prob_up", 0.5) if pos_ctx else 0.5
sr_levels = pos_ctx.get("sr_levels", {}) if pos_ctx else {}
```

### 2B. Format S/R levels for the prompt

Add this helper block after the above:

```python
# Format S/R levels for prompt
nearest_support = sr_levels.get("nearest_support")
nearest_resistance = sr_levels.get("nearest_resistance")
support_dist = sr_levels.get("support_distance_pct")
resistance_dist = sr_levels.get("resistance_distance_pct")

sr_line = "Support/Resistance: "
if nearest_support is not None and support_dist is not None:
    sr_line += f"Nearest Support=${nearest_support:.2f} ({support_dist:+.1f}%)"
else:
    sr_line += "Nearest Support=N/A"
sr_line += "  |  "
if nearest_resistance is not None and resistance_dist is not None:
    sr_line += f"Nearest Resistance=${nearest_resistance:.2f} ({resistance_dist:+.1f}%)"
else:
    sr_line += "Nearest Resistance=N/A"
```

### 2C. Inject into the prompt string

Find the CURRENT STATE section in the prompt (the f-string starting around line 228).
Add these 2 NEW lines AFTER the `News Sentiment Score` line (line 245) and BEFORE `News Context`:

```
ML Forecast: P(price_up_next_interval) = {ml_prob_up:.2f}  (GBM, retrained every 30min)
{sr_line}
```

The modified prompt section should look like:

```python
Position Context: {pos_str}
News Sentiment Score: {news_score:+.2f} (-1.0 to +1.0)
ML Forecast: P(price_up_next_interval) = {ml_prob_up:.2f}  (GBM, retrained every 30min)
{sr_line}
News Context: {news_ctx[:400]}
```

### 2D. Update the DECISION PROCESS instructions

In STEP 2, add a new sub-point after volatility layer:

```
  d) ML Forecast layer: Does the GBM model's P(up) support the direction?
     P(up) > 0.55 supports BUY. P(up) < 0.45 supports SELL. 0.45-0.55 is neutral.
```

Update the scoring to reference 4 layers instead of 3:
```
  Scoring:
    4/4 or 3/4 agree = High conviction signal → confidence 75-90
    2/4 agree = Actionable signal → confidence 60-74
    1/4 or 0/4 agree = Insufficient confluence → HOLD (confidence < 60)
```

In STEP 3, add a new risk check:

```
  - Support/Resistance Gate: Do NOT BUY if price is within 0.5% of nearest resistance.
    Do NOT SELL if price is within 0.5% of nearest support.
```

---

## Step 3: Verify

Run these commands to verify everything works:

```bash
# 1. All tests pass (including new tests from Task 1 and Task 2)
python -m pytest

# 2. Import check — no circular dependencies
python -c "from intelligence.ml.directional_predictor import DirectionalPredictor; print('OK')"
python -c "from data.features.support_resistance import SupportResistanceCalculator; print('OK')"

# 3. Quick live run (5 minutes)
python run_hour.py --minutes 5
```

Expected console output during live run should now show:
```
  [BTC-USD] Price: $63500.00
  [BTC-USD] Daily trend: NEUTRAL
  [BTC-USD] ML P(up)=0.58 | S=62800.00 R=64200.00
  [BTC-USD] Asking ATLAS-LLM...
  [BTC-USD] Decision: BUY (confidence=0.72)
```

---

## Commit Message

After all changes are verified:

```bash
git add -A
git commit -m "feat: add ML directional predictor and S/R level calculator to ATLAS prompt"
git push origin main
```

---

## Files Summary

### New Files Created
| File | Description |
|------|-------------|
| `src/intelligence/ml/__init__.py` | Empty package init |
| `src/intelligence/ml/directional_predictor.py` | GBM directional predictor class |
| `src/data/features/support_resistance.py` | Swing-based S/R level calculator |
| `src/tests/test_directional_predictor.py` | Unit tests for ML predictor |
| `src/tests/test_support_resistance.py` | Unit tests for S/R calculator |

### Modified Files
| File | What Changed |
|------|-------------|
| `run_hour.py` | Import + init + per-symbol compute + pos_context injection |
| `src/intelligence/strategies/atlas_strategy.py` | Read new fields + format prompt + update decision rules |

### Files NOT Modified
| File | Reason |
|------|--------|
| `requirements.txt` | scikit-learn already listed |
| `src/data/features/feature_engineer.py` | No changes needed |
| All existing test files | Must continue passing unchanged |
