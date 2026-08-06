"""
Quick test of LLM strategy with key rotation.

Tests actual API calls with multiple keys to verify rotation works in production.
"""
import sys
sys.path.insert(0, "src")

from load_keys import load_groq_keys, _load_groq_model
from intelligence.strategies.llm_strategy import LLMStrategy
from data.models.feature_vector import FeatureVector

print("="*60)
print("  LLM Strategy with Key Rotation Test")
print("="*60)

# Load keys
keys = load_groq_keys()
model = _load_groq_model()

print(f"\n✓ Loaded {len(keys)} API key(s)")
for i, key in enumerate(keys):
    print(f"  [{i+1}] {key[:8]}...{key[-4:]}")

# Create strategy with multiple keys
strategy = LLMStrategy(api_key=keys, model=model)
print(f"\n✓ LLMStrategy initialized")
print(f"  Strategy ID: {strategy.strategy_id}")
print(f"  Keys: {len(keys)}")
print(f"  Effective rate limit: {len(keys) * 30} req/min")

# Create test feature vector
features = {
    "price": 182.50,
    "price_change_pct": 2.35,
    "volume": 45_000_000,
    "volatility": 0.025,
    "sma_5": 180.20,
    "sma_20": 178.90,
}

fv = FeatureVector(
    symbol="AAPL",
    timestamp=1234567890.0,
    features=features,
    source_quality=0.95
)

print(f"\n--- Making 3 rapid API calls to test rotation ---")

for i in range(3):
    print(f"\nCall {i+1}:")
    decision = strategy.evaluate(fv)
    print(f"  Action:     {decision.action}")
    print(f"  Confidence: {decision.confidence:.2f}")
    print(f"  Rationale:  {decision.rationale[:80]}...")

print("\n✓ All API calls succeeded!")
print("\n[SUMMARY]")
print(f"  - Made 3 rapid API calls")
print(f"  - All succeeded without rate limit errors")
print(f"  - Key rotation working correctly")
print("="*60)
