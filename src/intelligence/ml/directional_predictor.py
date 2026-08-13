import time
import logging
import math
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

logger = logging.getLogger(__name__)

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

    def __init__(self, lookback: int = 100, retrain_ttl_seconds: float = 1800.0) -> None:
        self.lookback = lookback
        self.retrain_ttl_seconds = retrain_ttl_seconds
        
        self._models: dict[str, GradientBoostingClassifier] = {}
        self._last_trained: dict[str, float] = {}
        self._cache: dict[str, float] = {}

    @staticmethod
    def _ema(data: list[float], period: int) -> list[float]:
        """Calculates Exponential Moving Average."""
        if not data:
            return []
        alpha = 2 / (period + 1)
        ema = [data[0]]
        for i in range(1, len(data)):
            ema.append((data[i] - ema[-1]) * alpha + ema[-1])
        return ema

    @staticmethod
    def _compute_rsi(prices: list[float], period: int = 14) -> list[float]:
        """Calculates Relative Strength Index."""
        if len(prices) <= period:
            return [50.0] * len(prices)
            
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        # Initial averages
        gains = [d if d > 0 else 0.0 for d in deltas]
        losses = [-d if d < 0 else 0.0 for d in deltas]
        
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        rsis = [50.0] * period
        if avg_loss == 0:
            rsis.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsis.append(100.0 - (100.0 / (1.0 + rs)))
            
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            
            if avg_loss == 0:
                rsis.append(100.0)
            else:
                rs = avg_gain / avg_loss
                rsis.append(100.0 - (100.0 / (1.0 + rs)))
                
        return rsis

    @staticmethod
    def _compute_atr(prices: list[float], period: int = 14) -> list[float]:
        """Calculates Average True Range. Uses approximate true range assuming OHLC=price"""
        # Since we only have closing prices in the input, True Range simplifies 
        # to absolute price change from previous close.
        if len(prices) <= 1:
            return [0.0] * len(prices)
            
        trs = [0.0]  # First TR is 0
        for i in range(1, len(prices)):
            trs.append(abs(prices[i] - prices[i-1]))
            
        # Initial ATR is simple moving average of TR
        if len(trs) <= period:
            return [sum(trs)/len(trs)] * len(trs)
            
        atrs = [0.0] * (period - 1)
        atrs.append(sum(trs[:period]) / period)
        
        for i in range(period, len(trs)):
            atrs.append((atrs[-1] * (period - 1) + trs[i]) / period)
            
        return atrs

    @staticmethod
    def _compute_bollinger(prices: list[float], period: int = 20, num_std: float = 2.0) -> list[float]:
        """Calculates Bollinger %b."""
        if len(prices) < period:
            return [0.5] * len(prices)
            
        pct_b = [0.5] * (period - 1)
        
        for i in range(period - 1, len(prices)):
            window = prices[i - period + 1 : i + 1]
            mean = sum(window) / period
            variance = sum((x - mean) ** 2 for x in window) / period
            std_dev = math.sqrt(variance)
            
            upper = mean + (num_std * std_dev)
            lower = mean - (num_std * std_dev)
            
            if upper == lower:
                pct_b.append(0.5)
            else:
                pct_b.append((prices[i] - lower) / (upper - lower))
                
        return pct_b

    def _compute_features(self, prices: list[float], volumes: list[float]) -> np.ndarray:
        """Computes all features for the given series. Returns a 2D numpy array."""
        n = len(prices)
        
        rsi_14 = self._compute_rsi(prices, 14)
        ema_12 = self._ema(prices, 12)
        ema_26 = self._ema(prices, 26)
        
        macd_line = [0.0] * 25 + [ema_12[i] - ema_26[i] for i in range(25, n)]
        signal_line = [0.0] * 25 + self._ema(macd_line[25:], 9)
        macd_hist = [0.0] * n
        for i in range(33, n):
            macd_hist[i] = macd_line[i] - signal_line[i-25]
            
        bollinger_b = self._compute_bollinger(prices, 20)
        atr_5 = self._compute_atr(prices, 5)
        atr_20 = self._compute_atr(prices, 20)
        
        features = np.zeros((n, 7))
        
        for i in range(n):
            features[i, 0] = rsi_14[i]
            features[i, 1] = macd_hist[i]
            features[i, 2] = bollinger_b[i]
            features[i, 3] = atr_5[i] / atr_20[i] if atr_20[i] > 0 else 1.0
            
            if i >= 20:
                mean_vol = sum(volumes[i-20:i]) / 20
                features[i, 4] = volumes[i] / mean_vol if mean_vol > 0 else 1.0
            else:
                features[i, 4] = 1.0
                
            if i >= 5:
                features[i, 5] = (prices[i] - prices[i-5]) / prices[i-5] * 100
            if i >= 10:
                features[i, 6] = (prices[i] - prices[i-10]) / prices[i-10] * 100
                
        return features

    def predict(self, symbol: str, prices: list[float], volumes: list[float]) -> float:
        """
        Returns P(price_up_next_interval) as a float from 0.0 to 1.0.
        """
        n = len(prices)
        
        if n < self.lookback or n < 25:
            return 0.5
            
        now = time.monotonic()
        if symbol in self._models and (now - self._last_trained.get(symbol, 0)) < self.retrain_ttl_seconds:
            # Inference only on the last point
            features = self._compute_features(prices, volumes)
            X_latest = features[-1].reshape(1, -1)
            try:
                prob = self._models[symbol].predict_proba(X_latest)[0][1]
                prob = max(0.0, min(1.0, float(prob)))
                self._cache[symbol] = prob
                return prob
            except Exception as e:
                logger.warning(f"Failed to infer from model for {symbol}: {e}")
                return self._cache.get(symbol, 0.5)

        # Retrain needed
        try:
            features = self._compute_features(prices, volumes)
            
            X_train = []
            y_train = []
            
            start_idx = max(14, 20)
            for i in range(start_idx, n - 1):
                X_train.append(features[i])
                label = 1 if prices[i+1] > prices[i] else 0
                y_train.append(label)
                
            if len(X_train) < 10:
                return 0.5
                
            X_train = np.array(X_train)
            y_train = np.array(y_train)
            
            # Use fixed parameters as specified
            model = GradientBoostingClassifier(
                n_estimators=50,
                max_depth=3,
                learning_rate=0.1,
                random_state=42,
            )
            model.fit(X_train, y_train)
            
            self._models[symbol] = model
            self._last_trained[symbol] = now
            
            # Predict for current state
            X_latest = features[-1].reshape(1, -1)
            prob = model.predict_proba(X_latest)[0][1]
            prob = max(0.0, min(1.0, float(prob)))
            
            self._cache[symbol] = prob
            return prob
            
        except Exception as e:
            logger.warning(f"Failed to train directional predictor for {symbol}: {e}")
            return 0.5
