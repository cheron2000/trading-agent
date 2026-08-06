"""
test_llm_quick.py — Quick LLM Strategy Diagnostic Test

Tests the LLM strategy with a strong bullish signal to verify:
1. GROQ API key is loaded correctly
2. LLM client can connect to Groq
3. LLM generates intelligent decisions
4. JSON parsing works correctly
5. Decision validation passes

Usage:
    python test_llm_quick.py

Expected Output:
    LLM Decision:
      Action:     BUY
      Confidence: 0.75-0.95
      Rationale:  <intelligent market analysis>

If this test fails, check:
- GROQ_API_KEY in keys.env
- Internet connection
- Groq API status (console.groq.com)
"""
import sys
sys.path.insert(0, "src")

from datetime import datetime, timezone
from data.models.feature_vector import FeatureVector
from intelligence.strategies.llm_strategy import LLMStrategy
from load_keys import load_groq_key

# Load key
groq_key, groq_model = load_groq_key()
print(f"GROQ Key: {groq_key[:20] if groq_key else 'MISSING'}... Model: {groq_model}")

if not groq_key:
    print("\n❌ ERROR: GROQ_API_KEY not found in keys.env")
    print("Add: GROQ_API_KEY=gsk_your_key_here")
    print("Get key: https://console.groq.com")
    sys.exit(1)

# Create strategy
strategy = LLMStrategy(api_key=groq_key, model=groq_model)
print(f"Strategy ID: {strategy.strategy_id}")

# Create test feature vector with strong bullish signal
fv = FeatureVector(
    symbol="AAPL",
    timestamp=datetime.now(timezone.utc),
    features={
        "price": 182.29,
        "price_change_pct": 5.8,  # Strong positive move
        "volume": 50000000.0,
        "volatility": 0.02,
        "sma_5": 180.0,
        "sma_20": 175.0,
    },
    source_quality=1.0,
)

print(f"\n{'='*60}")
print("Testing LLM Strategy with bullish signal...")
print(f"{'='*60}")
print(f"Symbol: {fv.symbol}")
print(f"Price: ${fv.features['price']:.2f}")
print(f"Price Change: {fv.features['price_change_pct']:+.2f}%")
print(f"Volume: {fv.features['volume']:,.0f}")
print(f"{'='*60}\n")

try:
    # Evaluate
    decision = strategy.evaluate(fv)

    print("✅ LLM Decision:")
    print(f"  Action:     {decision.action}")
    print(f"  Confidence: {decision.confidence:.2f}")
    print(f"  Rationale:  {decision.rationale}")
    print(f"  Strategy:   {decision.strategy_id}")
    print(f"\n{'='*60}")
    
    if decision.action == "BUY":
        print("✅ TEST PASSED: LLM correctly identified bullish signal")
    elif decision.action == "HOLD":
        print("⚠️  TEST WARNING: LLM returned HOLD (conservative)")
    else:
        print("❌ TEST FAILED: LLM returned SELL for bullish signal")
        
except Exception as exc:
    print(f"\n❌ TEST FAILED: {exc}")
    print("\nCheck:")
    print("- GROQ_API_KEY is valid")
    print("- Internet connection")
    print("- Groq API status: https://status.groq.com")
    sys.exit(1)
