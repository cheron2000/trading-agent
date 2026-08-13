"""
test_groq_key.py — Groq API key diagnostics + live LLM decision test.

Tests the Groq key against 3 scenarios:
  1. Basic connectivity  — can we reach the API?
  2. JSON mode output    — does the model return valid JSON?
  3. Real trading prompt — does the LLM make a valid BUY/SELL/HOLD decision?

Usage:
    python test_groq_key.py                  # reads key from keys.env
    python test_groq_key.py YOUR_GROQ_KEY    # explicit key
"""
import sys
import json
import time
from pathlib import Path
from urllib.request import urlopen, Request
import urllib.request
from urllib.error import HTTPError, URLError

# ANSI colours
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL    = "llama-3.1-8b-instant"

# Fake feature vector for a realistic trading prompt test
FAKE_FEATURES = {
    "price_change_pct": 2.34,
    "price_latest":     333.26,
    "price_mean":       330.10,
    "price_std":        4.21,
    "volume_mean":      62_000_000,
    "volume_total":     310_000_000,
    "high":             335.10,
    "low":              328.90,
}


def call_groq(api_key: str, messages: list, json_mode: bool = False) -> tuple[bool, str, float]:
    """Make a Groq API call. Returns (success, response_text, latency_ms)."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 256,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    body = json.dumps(payload).encode("utf-8")
    req = Request(
        GROQ_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "python-httpx/0.27.0",
            "Accept": "application/json",
        },
        method="POST",
    )

    t0 = time.monotonic()
    try:
        with urlopen(req, timeout=12) as resp:
            elapsed = (time.monotonic() - t0) * 1000
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            return True, content, elapsed
    except HTTPError as err:
        elapsed = (time.monotonic() - t0) * 1000
        body_str = err.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(body_str)
            msg = err_json.get("error", {}).get("message", body_str)
        except Exception:
            msg = body_str
        return False, f"HTTP {err.code}: {msg}", elapsed
    except URLError as err:
        elapsed = (time.monotonic() - t0) * 1000
        return False, f"Network error: {err.reason}", elapsed
    except Exception as err:
        elapsed = (time.monotonic() - t0) * 1000
        return False, f"Unexpected error: {err}", elapsed


def test_basic(api_key: str) -> tuple[bool, str, float]:
    """Test 1: Ping API with 'ping' prompt."""
    messages = [{"role": "user", "content": "Reply with 'pong' only."}]
    ok, text, latency = call_groq(api_key, messages)
    if ok:
        snippet = text.strip()[:60]
        return True, f"Response: {snippet!r}", latency
    return False, text, latency


def test_json_mode(api_key: str) -> tuple[bool, str, float]:
    """Test 2: Enforce JSON response format."""
    messages = [
        {"role": "system", "content": "You are a helper that outputs JSON only."},
        {"role": "user",   "content": "Return a JSON object with keys 'status' (string) and 'code' (integer 200)."},
    ]
    ok, text, latency = call_groq(api_key, messages, json_mode=True)
    if not ok:
        return False, text, latency
    try:
        parsed = json.loads(text)
        return True, f"Valid JSON: {parsed}", latency
    except json.JSONDecodeError:
        return False, f"Not valid JSON: {text!r}", latency


def test_trading_decision(api_key: str) -> tuple[bool, str, float]:
    """Test 3: Pass a real feature vector prompt and check decision structure."""
    prompt = f"""You are the LLM strategy module for an algorithmic trading system.
Given the following features for TSLA:
Price: ${FAKE_FEATURES['price_latest']} (Change: {FAKE_FEATURES['price_change_pct']}%)
Mean:  ${FAKE_FEATURES['price_mean']}   Std: ${FAKE_FEATURES['price_std']}
Volume: {FAKE_FEATURES['volume_mean']:,}
High:  ${FAKE_FEATURES['high']}   Low: ${FAKE_FEATURES['low']}

Respond with a JSON object containing:
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": <float 0.0-1.0>,
  "rationale": "<1-2 sentence explanation citing specific numbers>"
"""
    messages = [
        {"role": "system", "content": "You are an AI financial analyst. Respond with JSON only."},
        {"role": "user",   "content": prompt},
    ]
    ok, text, latency = call_groq(api_key, messages, json_mode=True)
    if not ok:
        return False, text, latency
    try:
        parsed = json.loads(text)
        action = parsed.get("action", "").upper()
        conf   = parsed.get("confidence", 0.0)
        rat    = parsed.get("rationale", "")
        if action in ("BUY", "SELL", "HOLD") and 0.0 <= float(conf) <= 1.0:
            msg = f"Decision: {BOLD}{action}{RESET} (conf: {conf:.2f}) — {rat[:80]}..."
            return True, msg, latency
        return False, f"Invalid decision fields: {parsed}", latency
    except Exception as err:
        return False, f"Failed to parse decision: {err} (raw: {text!r})", latency


def main() -> None:
    if len(sys.argv) > 1:
        api_key = sys.argv[1].strip()
        source  = "CLI argument"
    else:
        try:
            from load_keys import load_groq_key
            api_key, model = load_groq_key()
            if not api_key:
                print(f"\n{RED}No GROQ_API_KEY found in keys.env.{RESET}")
                print("Add it:  GROQ_API_KEY=gsk_your_key_here")
                sys.exit(1)
            source = f"keys.env (model: {model})"
        except Exception as exc:
            print(f"\n{RED}Could not load keys.env: {exc}{RESET}")
            sys.exit(1)

    masked = f"{api_key[:8]}{'*' * max(0, len(api_key)-12)}{api_key[-4:]}"

    print(f"\n==========================================================")
    print(f"  Groq API Key Test")
    print(f"==========================================================")
    print(f"  Key:    {CYAN}{masked}{RESET}")
    print(f"  Source: {source}")
    print(f"  Model:  {MODEL}\n")

    tests = [
        ("Basic connectivity",    lambda: test_basic(api_key)),
        ("JSON mode output",      lambda: test_json_mode(api_key)),
        ("Trading decision (LLM)", lambda: test_trading_decision(api_key)),
    ]

    passed = 0
    for i, (label, fn) in enumerate(tests):
        ok, msg, latency = fn()
        icon = f"{GREEN}[OK] PASS{RESET}" if ok else f"{RED}[X] FAIL{RESET}"
        print(f"  [{i+1}/3] {label:<28} {icon}  ({latency:.0f}ms)")
        for line in msg.split("\n"):
            print(f"          {line}")
        if ok:
            passed += 1
        print()

    print("=" * 58)
    if passed == 3:
        print(f"  {GREEN}{BOLD}[OK] Groq key fully operational — {passed}/3 tests passed.{RESET}")
        print("  LLM trading decisions are ENABLED.")
        print("  Run:  python run_hour.py")
    elif passed > 0:
        print(f"  {YELLOW}{BOLD}[!] Partial — {passed}/3 tests passed.{RESET}")
    else:
        print(f"  {RED}{BOLD}[X] Key not working — check key and network.{RESET}")
    print("=" * 58)


if __name__ == "__main__":
    main()
