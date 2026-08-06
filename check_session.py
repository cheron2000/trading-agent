"""
Quick session status check script.

Shows:
- Trading session status
- API key configuration
- Rate limit info
- Dashboard link
"""
import sys
from datetime import datetime
sys.path.insert(0, ".")

from load_keys import load_groq_keys, _load_groq_model

print("="*60)
print("  AI Trading OS — Session Status")
print("="*60)

# Check keys
keys = load_groq_keys()
model = _load_groq_model()

print(f"\n✓ API Keys Loaded: {len(keys)}")
for i, key in enumerate(keys):
    masked = f"{key[:8]}...{key[-4:]}"
    print(f"  [{i+1}] {masked}")

print(f"\n✓ Model: {model}")
print(f"✓ Effective Rate Limit: {len(keys) * 30} req/min")
print(f"✓ Per-Key Limit: 30 req/min")

if len(keys) > 1:
    print(f"\n✓ Key Rotation: ENABLED")
    print(f"  - On 429 error: Instant rotation to next key")
    print(f"  - Exponential backoff: Only after all {len(keys)} keys exhausted")
else:
    print(f"\n⚠ Key Rotation: DISABLED (only 1 key)")

print(f"\n📊 Dashboard: http://127.0.0.1:5000")
print(f"🕒 Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

print("="*60)
