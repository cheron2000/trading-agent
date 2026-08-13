import time
import random
from intelligence.ml.directional_predictor import DirectionalPredictor


def test_predict_neutral_with_insufficient_data():
    predictor = DirectionalPredictor()
    prices = [100.0] * 20
    volumes = [10.0] * 20
    assert predictor.predict("TEST", prices, volumes) == 0.5


def test_predict_returns_valid_probability():
    predictor = DirectionalPredictor(lookback=100)
    prices = [100 + i * 0.1 + random.uniform(-0.5, 0.5) for i in range(150)]
    volumes = [100.0] * 150
    prob = predictor.predict("TEST1", prices, volumes)
    assert 0.0 <= prob <= 1.0


def test_predict_caching_ttl():
    predictor = DirectionalPredictor(lookback=100, retrain_ttl_seconds=10.0)
    prices = [100 + random.uniform(-1, 1) for _ in range(150)]
    volumes = [100.0] * 150

    t1 = time.time()
    prob1 = predictor.predict("TEST2", prices, volumes)
    t2 = time.time()

    t3 = time.time()
    prob2 = predictor.predict("TEST2", prices, volumes)
    t4 = time.time()

    # First call trains model, should take longer than the second which is cached inference
    train_duration = t2 - t1
    infer_duration = t4 - t3

    assert prob1 == prob2
    assert infer_duration < train_duration or infer_duration < 0.1


def test_predict_with_trending_data():
    predictor = DirectionalPredictor(lookback=100)
    random.seed(42)
    # Upward drift but with enough noise to have some negative labels
    prices = [100 + (i * 0.5) + random.uniform(-2, 2) for i in range(150)]
    volumes = [100.0] * 150
    prob = predictor.predict("UPTREND", prices, volumes)

    # In a clear uptrend, prediction should favor up (label 1)
    assert prob > 0.5
