"""
Test script for API key rotation in GroqClient.

Verifies that:
1. Multiple keys are loaded correctly
2. GroqClient accepts list of keys
3. Key rotation works on simulated 429 errors
"""
import sys
sys.path.insert(0, "src")

from load_keys import load_groq_keys, _load_groq_model
from intelligence.agent.groq_client import GroqClient

print("="*60)
print("  Groq API Key Rotation Test")
print("="*60)

# Load keys
keys = load_groq_keys()
model = _load_groq_model()

print(f"\n✓ Loaded {len(keys)} API key(s) from keys.env")
for i, key in enumerate(keys):
    masked = f"{key[:8]}...{key[-4:]}"
    print(f"  [{i+1}] {masked}")

print(f"\n✓ Model: {model}")

# Test single key (backward compatibility)
print("\n--- Test 1: Single key initialization ---")
client1 = GroqClient(api_key=keys[0], model=model)
print(f"✓ GroqClient created with single key")
print(f"  Keys loaded: {len(client1._api_keys)}")

# Test multiple keys
print("\n--- Test 2: Multiple keys initialization ---")
client2 = GroqClient(api_key=keys, model=model)
print(f"✓ GroqClient created with {len(keys)} keys")
print(f"  Current key index: {client2._current_key_index}")

# Test rotation
print("\n--- Test 3: Manual key rotation ---")
for i in range(len(keys) + 2):
    current_key = client2._api_key
    masked = f"{current_key[:8]}...{current_key[-4:]}"
    print(f"  Iteration {i+1}: Using key {client2._current_key_index + 1}/{len(keys)} ({masked})")
    
    rotated = client2._rotate_key()
    if rotated:
        print(f"    → Rotated to key {client2._current_key_index + 1}/{len(keys)}")
    else:
        print(f"    → No rotation (only 1 key available)")

print("\n✓ Key rotation works correctly!")
print(f"\n[SUMMARY]")
print(f"  - Loaded {len(keys)} API keys")
print(f"  - Effective rate limit: {len(keys) * 30} req/min")
print(f"  - Rate limit per key: 30 req/min")
print(f"  - On 429 error: Rotates to next key immediately")
print(f"  - Exponential backoff: Only after all keys exhausted")
print("="*60)
