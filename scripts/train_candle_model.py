"""
scripts/train_candle_model.py
================================
Trains a RandomForestClassifier on synthetic + fixture-seeded OHLCV candle
data and saves to models/candle_rf.pkl.

Two modes:
  1. Live (default): fetches 60d 5m history from yfinance
  2. Synthetic (fallback / --synthetic): generates GBM candles from fixture prices

Usage:
    python scripts/train_candle_model.py              # tries live, falls back to synthetic
    python scripts/train_candle_model.py --synthetic  # force synthetic
"""
from __future__ import annotations

import pickle
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report

from intelligence.candle.candle_features import extract

SYMBOLS   = ["AAPL", "MSFT", "GOOGL", "BTC-USD", "ETH-USD", "TSLA"]
INTERVAL  = "5m"
WINDOW    = 50
LABEL_FWD = 3
BUY_THR   = 0.01
SELL_THR  = -0.01
MODEL_OUT = Path(__file__).parent.parent / "models" / "candle_rf.pkl"

FEATURE_NAMES = [
    "body_size_mean", "body_size_last", "upper_wick_mean", "lower_wick_mean",
    "close_above_open_pct", "momentum_3", "momentum_10", "volume_trend",
    "engulfing_bullish", "engulfing_bearish", "doji_last", "high_low_range_pct",
]

# Seed prices from fixture data (last known prices)
_SEED_PRICES = {
    "AAPL": 185.84, "MSFT": 397.67, "GOOGL": 153.31,
    "BTC-USD": 49188.71, "ETH-USD": 2110.18, "TSLA": 229.56,
}


def _generate_synthetic_candles(seed_price: float, n: int = 2000, vol: float = 0.008) -> list[dict]:
    """Generate n synthetic 5m OHLCV candles via Geometric Brownian Motion."""
    rng = np.random.default_rng(42)
    candles = []
    price = seed_price
    base_vol = seed_price * 1000  # rough volume baseline

    for i in range(n):
        ret = rng.normal(0.0001, vol)
        open_p = price
        close_p = price * (1 + ret)
        high_p  = max(open_p, close_p) * (1 + abs(rng.normal(0, vol * 0.5)))
        low_p   = min(open_p, close_p) * (1 - abs(rng.normal(0, vol * 0.5)))
        volume  = base_vol * rng.lognormal(0, 0.4)
        candles.append({
            "open": open_p, "high": high_p, "low": low_p,
            "close": close_p, "volume": volume,
            "timestamp": f"2024-01-01T{i:05d}",
        })
        price = close_p

    return candles


def _build_dataset(candles: list[dict]) -> tuple[list, list]:
    X, y = [], []
    closes = [c["close"] for c in candles]
    for i in range(WINDOW, len(candles) - LABEL_FWD):
        window = candles[i - WINDOW: i]
        feats = extract(window)
        if not feats:
            continue
        ret = (closes[i + LABEL_FWD] - closes[i - 1]) / closes[i - 1]
        label = "BUY" if ret >= BUY_THR else ("SELL" if ret <= SELL_THR else "HOLD")
        X.append([feats[k] for k in FEATURE_NAMES])
        y.append(label)
    return X, y


def _fetch_via_tor(sym: str, interval: str = "5m", range_: str = "60d") -> list[dict]:
    """Fetch OHLCV candles via Yahoo Finance JSON API through Tor SOCKS5 proxy."""
    import requests
    proxy = "socks5h://127.0.0.1:9150"
    session = requests.Session()
    session.proxies = {"http": proxy, "https": proxy}

    # Yahoo Finance chart API — returns full OHLCV
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        f"?interval={interval}&range={range_}"
    )
    resp = session.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    data = resp.json()
    result = data["chart"]["result"][0]
    timestamps = result.get("timestamp", [])
    q = result["indicators"]["quote"][0]
    opens   = q.get("open",   [])
    highs   = q.get("high",   [])
    lows    = q.get("low",    [])
    closes  = q.get("close",  [])
    volumes = q.get("volume", [])

    candles = []
    for i in range(len(closes)):
        if closes[i] is None or opens[i] is None:
            continue
        candles.append({
            "open":      float(opens[i]  or closes[i]),
            "high":      float(highs[i]  or closes[i]),
            "low":       float(lows[i]   or closes[i]),
            "close":     float(closes[i]),
            "volume":    float(volumes[i] or 0) if i < len(volumes) else 0.0,
            "timestamp": str(timestamps[i]) if i < len(timestamps) else str(i),
        })
    return candles


def _try_live() -> tuple[list, list]:
    X_all, y_all = [], [];
    for sym in SYMBOLS:
        print(f"  Fetching {sym} via Tor...")
        candles = _fetch_via_tor(sym, interval=INTERVAL, range_="60d")
        if len(candles) < WINDOW + LABEL_FWD + 5:
            raise ValueError(f"Not enough candles for {sym}: got {len(candles)}")
        print(f"    {sym}: {len(candles)} candles")
        X, y = _build_dataset(candles)
        X_all.extend(X)
        y_all.extend(y)
    return X_all, y_all


def _synthetic() -> tuple[list, list]:
    X_all, y_all = [], []
    for sym in SYMBOLS:
        seed = _SEED_PRICES.get(sym, 100.0)
        vol  = 0.015 if "BTC" in sym or "ETH" in sym else 0.008
        print(f"  Generating synthetic candles for {sym} (seed=${seed:.2f}, vol={vol})...")
        candles = _generate_synthetic_candles(seed, n=3000, vol=vol)
        X, y = _build_dataset(candles)
        X_all.extend(X)
        y_all.extend(y)
    return X_all, y_all


# --- Main ---
force_synthetic = "--synthetic" in sys.argv

X_all, y_all = [], []

if not force_synthetic:
    print("Attempting live yfinance fetch...")
    try:
        X_all, y_all = _try_live()
        print(f"Live fetch succeeded — {len(X_all)} samples")
    except Exception as exc:
        print(f"Live fetch failed ({exc}) — falling back to synthetic data")
        X_all, y_all = _synthetic()
else:
    print("Synthetic mode (--synthetic flag)")
    X_all, y_all = _synthetic()

if not X_all:
    print("No training data — aborting.")
    sys.exit(1)

print(f"\nTotal samples : {len(X_all)}")
print(f"Label dist    : { {l: y_all.count(l) for l in sorted(set(y_all))} }")

clf = RandomForestClassifier(
    n_estimators=100, max_depth=6, random_state=42, n_jobs=-1,
    class_weight="balanced",  # compensate for HOLD dominance
)
clf.fit(X_all, y_all)

print("\nClassification report (in-sample):")
print(classification_report(y_all, clf.predict(X_all)))

MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
with open(MODEL_OUT, "wb") as fh:
    pickle.dump(clf, fh)

print(f"Model saved to: {MODEL_OUT}")
