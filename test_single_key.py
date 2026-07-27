"""
test_single_key.py — Quick single-key live test against Alpha Vantage.

Tests ONE key against 3 endpoints:
  1. AAPL equity quote     (GLOBAL_QUOTE)
  2. MSFT equity quote     (GLOBAL_QUOTE)
  3. BTC-USD crypto rate   (CURRENCY_EXCHANGE_RATE)

Usage:
    python test_single_key.py YOUR16CHARAVKEY1
"""
import sys
import json
import time
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

BASE_URL = "https://www.alphavantage.co/query"

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def raw_get(params: dict) -> dict:
    from urllib.parse import urlencode
    url = f"{BASE_URL}?{urlencode(params)}"
    with urlopen(url, timeout=15) as r:
        return json.loads(r.read().decode())


def test_equity(key: str, symbol: str) -> tuple[bool, str]:
    """Test equity GLOBAL_QUOTE endpoint."""
    try:
        data = raw_get({"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": key})

        if "Note" in data:
            return False, f"Per-minute rate limit: {data['Note'][:80]}"
        if "Information" in data:
            info = data["Information"]
            if "rate limit" in info.lower() or "25 requests" in info.lower():
                return False, "Daily quota exhausted (25 req/day). Resets midnight EST."
            return False, f"API info: {info[:100]}"
        if "Error Message" in data:
            return False, f"API error: {data['Error Message'][:100]}"

        quote = data.get("Global Quote", {})
        if not quote or not quote.get("05. price"):
            return False, f"Empty response — raw: {json.dumps(data)[:150]}"

        price   = float(quote["05. price"])
        volume  = int(float(quote.get("06. volume", 0)))
        day     = quote.get("07. latest trading day", "?")
        chg_pct = quote.get("10. change percent", "?")
        return True, f"${price:.2f}  vol={volume:,}  day={day}  chg={chg_pct}"

    except HTTPError as e:
        return False, f"HTTP {e.code}: {e.reason}"
    except URLError as e:
        return False, f"Network error: {e}"


def test_crypto(key: str, base: str = "BTC") -> tuple[bool, str]:
    """Test crypto CURRENCY_EXCHANGE_RATE endpoint."""
    try:
        data = raw_get({
            "function": "CURRENCY_EXCHANGE_RATE",
            "from_currency": base,
            "to_currency": "USD",
            "apikey": key,
        })

        if "Note" in data:
            return False, f"Per-minute rate limit: {data['Note'][:80]}"
        if "Information" in data:
            info = data["Information"]
            if "rate limit" in info.lower() or "25 requests" in info.lower():
                return False, "Daily quota exhausted (25 req/day). Resets midnight EST."
            return False, f"API info: {info[:100]}"
        if "Error Message" in data:
            return False, f"API error: {data['Error Message'][:100]}"

        rate_info = data.get("Realtime Currency Exchange Rate", {})
        if not rate_info or not rate_info.get("5. Exchange Rate"):
            return False, f"Empty crypto response — raw: {json.dumps(data)[:150]}"

        price     = float(rate_info["5. Exchange Rate"])
        refreshed = rate_info.get("6. Last Refreshed", "?")
        return True, f"${price:,.2f}  refreshed={refreshed}"

    except HTTPError as e:
        return False, f"HTTP {e.code}: {e.reason}"
    except URLError as e:
        return False, f"Network error: {e}"


def main() -> None:
    if len(sys.argv) < 2:
        print(f"\n{BOLD}Usage:{RESET}  python test_single_key.py YOUR_API_KEY")
        print(f"Example: python test_single_key.py YOUR16CHARAVKEY1\n")
        sys.exit(1)

    key = sys.argv[1].strip()
    masked = f"{key[:4]}{'*' * max(0, len(key)-8)}{key[-4:]}" if len(key) > 8 else key

    print(f"\n{BOLD}{'='*55}{RESET}")
    print(f"{BOLD}  Single Key Live Test — Alpha Vantage{RESET}")
    print(f"{BOLD}{'='*55}{RESET}")
    print(f"  Key: {CYAN}{masked}{RESET}\n")

    tests = [
        ("AAPL  (equity)",  lambda: test_equity(key, "AAPL")),
        ("MSFT  (equity)",  lambda: test_equity(key, "MSFT")),
        ("BTC-USD (crypto)", lambda: test_crypto(key, "BTC")),
    ]

    passed = 0
    for i, (label, fn) in enumerate(tests):
        ok, msg = fn()
        icon = f"{GREEN}✓ PASS{RESET}" if ok else f"{RED}✗ FAIL{RESET}"
        print(f"  [{i+1}/3] {label:<22} {icon}")
        print(f"          {msg}")
        if ok:
            passed += 1
        # Respect 5 req/min — sleep between calls
        if i < len(tests) - 1:
            print(f"          {YELLOW}(waiting 12s for rate limit...){RESET}")
            time.sleep(12)
        print()

    print(f"{'─'*55}")
    if passed == len(tests):
        print(f"  {GREEN}{BOLD}✓ Key is fully operational — {passed}/{len(tests)} tests passed.{RESET}")
        print(f"  Ready to use. Run the simulation:")
        print(f"    python run_simulation.py --live")
    elif passed > 0:
        print(f"  {YELLOW}{BOLD}⚠ Partial — {passed}/{len(tests)} tests passed.{RESET}")
        print(f"  Some endpoints may be rate-limited.")
    else:
        print(f"  {RED}{BOLD}✗ Key not working — 0/{len(tests)} tests passed.{RESET}")
        print(f"  Check if daily quota is exhausted or key is invalid.")
    print(f"{BOLD}{'='*55}{RESET}\n")


if __name__ == "__main__":
    main()
