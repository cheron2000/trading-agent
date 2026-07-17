"""
test_av_key.py — Alpha Vantage API key diagnostics tool.

Usage:
    python test_av_key.py KEY1
    python test_av_key.py KEY1 KEY2 KEY3 ...

Checks each key against the Alpha Vantage API and reports:
  - VALID      : key works, returns live price
  - RATE_LIMITED: key is valid but daily quota exhausted (resets midnight EST)
  - INVALID    : key is rejected by Alpha Vantage
  - ERROR      : network or unexpected error

Also shows the live AAPL price if any key is healthy.
"""
import sys
import json
import time
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

BASE_URL = "https://www.alphavantage.co/query"

# ── ANSI colours (Windows 10+ supports these) ──────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def check_key(api_key: str) -> dict:
    """Test a single API key. Returns a result dict."""
    url = (
        f"{BASE_URL}?function=GLOBAL_QUOTE"
        f"&symbol=AAPL"
        f"&apikey={api_key}"
    )
    try:
        with urlopen(url, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
    except HTTPError as exc:
        if exc.code == 429:
            return {"status": "RATE_LIMITED", "message": "HTTP 429 Too Many Requests", "key": api_key}
        return {"status": "ERROR", "message": f"HTTP {exc.code}: {exc.reason}", "key": api_key}
    except URLError as exc:
        return {"status": "ERROR", "message": f"Network error: {exc}", "key": api_key}
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc), "key": api_key}

    # ── Parse Alpha Vantage response ──────────────────────────────────────
    raw_response = json.dumps(data)

    # Daily rate limit exhausted
    info = data.get("Information", "")
    if info and ("rate limit" in info.lower() or "25 requests per day" in info.lower()):
        return {
            "status": "RATE_LIMITED",
            "message": "Daily quota exhausted (25 req/day free tier). Resets at midnight EST.",
            "key": api_key,
            "raw": info,
        }

    # Per-minute rate limit
    note = data.get("Note", "")
    if note and "minute" in note.lower():
        return {
            "status": "RATE_LIMITED_PER_MIN",
            "message": "Per-minute limit hit (5 req/min). Wait 60s.",
            "key": api_key,
            "raw": note,
        }

    # Invalid key
    if info and ("invalid api key" in info.lower() or "invalid api call" in info.lower()):
        return {
            "status": "INVALID",
            "message": info,
            "key": api_key,
        }

    # Explicit error
    error_msg = data.get("Error Message", "")
    if error_msg:
        return {
            "status": "INVALID",
            "message": error_msg,
            "key": api_key,
        }

    # Successful quote
    quote = data.get("Global Quote", {})
    if quote and quote.get("05. price"):
        price = float(quote["05. price"])
        volume = int(float(quote.get("06. volume", 0)))
        day = quote.get("07. latest trading day", "unknown")
        change_pct = quote.get("10. change percent", "0%")
        return {
            "status": "VALID",
            "message": f"AAPL @ ${price:.2f}  vol={volume:,}  day={day}  chg={change_pct}",
            "key": api_key,
            "price": price,
        }

    # Empty response — unusual
    return {
        "status": "ERROR",
        "message": f"Unexpected empty response: {raw_response[:200]}",
        "key": api_key,
    }


def mask_key(key: str) -> str:
    """Show first 4 and last 4 chars only."""
    if len(key) <= 8:
        return key
    return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"


def main() -> None:
    keys = sys.argv[1:]

    if not keys:
        # Auto-load from keys.env if no args given
        try:
            sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
            from load_keys import load_av_keys
            keys = load_av_keys()
            print(f"\n{CYAN}No keys passed — loaded {len(keys)} key(s) from keys.env{RESET}")
        except Exception as exc:
            print(f"\n{BOLD}Usage:{RESET}  python test_av_key.py KEY1 [KEY2 KEY3 ...]")
            print(f"  Or add keys to keys.env and run without arguments.")
            print(f"\n{RED}Could not load keys.env: {exc}{RESET}\n")
            sys.exit(1)

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  Alpha Vantage API Key Diagnostics{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")
    print(f"  Testing {len(keys)} key(s)...\n")

    valid_count = 0
    rate_limited_count = 0
    invalid_count = 0
    error_count = 0

    for i, key in enumerate(keys):
        masked = mask_key(key)
        result = check_key(key)
        status = result["status"]

        if status == "VALID":
            icon = f"{GREEN}✓ VALID{RESET}"
            valid_count += 1
        elif status in ("RATE_LIMITED", "RATE_LIMITED_PER_MIN"):
            icon = f"{YELLOW}⚠ RATE_LIMITED{RESET}"
            rate_limited_count += 1
        elif status == "INVALID":
            icon = f"{RED}✗ INVALID{RESET}"
            invalid_count += 1
        else:
            icon = f"{RED}? ERROR{RESET}"
            error_count += 1

        print(f"  [{i+1}/{len(keys)}] {CYAN}{masked}{RESET}  →  {icon}")
        print(f"         {result['message']}")
        print()

        # Sleep between keys to avoid per-minute rate limit
        if i < len(keys) - 1:
            time.sleep(12)

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}  Summary{RESET}")
    print(f"{'─'*60}")
    print(f"  {GREEN}Valid (ready to use)  : {valid_count}{RESET}")
    print(f"  {YELLOW}Rate limited (quota)  : {rate_limited_count}{RESET}")
    print(f"  {RED}Invalid               : {invalid_count}{RESET}")
    print(f"  {RED}Error                 : {error_count}{RESET}")
    print()

    if rate_limited_count > 0 and valid_count == 0:
        print(f"  {YELLOW}ℹ  All keys are rate-limited for today.{RESET}")
        print(f"  {YELLOW}   Quota resets at midnight US Eastern Time.{RESET}")
        print(f"   Register more free keys at: https://www.alphavantage.co/support/#api-key")
        print(f"   Add new keys to keys.env one per line or comma-separated.")
    elif valid_count > 0:
        print(f"  {GREEN}✓  {valid_count} key(s) ready.{RESET}")
        print(f"   Run the simulation:")
        print(f"     python run_simulation.py --live")
        print(f"   (keys.env is loaded automatically)")

    print(f"{BOLD}{'='*60}{RESET}\n")


if __name__ == "__main__":
    main()
