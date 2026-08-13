# Build Instructions: ML Predictor & Support/Resistance for ATLAS Strategy

This folder contains precise, actionable build instructions for an AI agent
to implement two new intelligence modules that will be injected into the
ATLAS LLM prompt as additional decision-support data.

## Build Order (STRICT)
1. **Read `01_ML_PREDICTOR.md` first** → Build the XGBoost directional predictor
2. **Read `02_SUPPORT_RESISTANCE.md` second** → Build the S/R level calculator
3. **Read `03_INTEGRATION.md` last** → Wire both modules into `run_hour.py` and the ATLAS prompt

## Critical Context
- The project root is the `ai-trading-os/` directory
- All source code lives under `src/` with Python package imports relative to `src/`
- `run_hour.py` does `sys.path.insert(0, "src")` so imports work as `from data.models.xxx import Xxx`
- The `FeatureVector` is a frozen dataclass — do NOT mutate it directly; copy `fv.features` into a new dict
- The ATLAS prompt is built in `src/intelligence/strategies/atlas_strategy.py` method `_build_atlas_prompt()`
- Position context dict is assembled in `run_hour.py` around line 648-664 and passed to `strategy.evaluate_with_context(fv, position_context=pos_context)`
- All 57 existing tests MUST continue to pass after your changes (`python -m pytest`)
- `requirements.txt` already includes `scikit-learn>=1.3.0` — no new dependencies needed for XGBoost since we'll use sklearn's `GradientBoostingClassifier` (equivalent performance, no extra install)
