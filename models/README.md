# models/

Serialized ML models for the Candle Intelligence Layer.

## candle_rf.pkl

RandomForestClassifier trained on 60 days of 5m OHLCV candle history.

Generate with:
```bash
python scripts/train_candle_model.py
```
