"""
load_keys.py — API key loader for the AI Trading OS.

Reads keys.env and returns the list of Alpha Vantage API keys.
Supports two formats in the same file:

    AV_KEYS=KEY1,KEY2,KEY3          # comma-separated list
    AV_KEY_1=ABCD1234EFGH5678       # individual numbered keys
    AV_KEY_2=WXYZ9876MNOP4321

Both formats can coexist — all keys are merged and deduplicated.
Keys are returned in the order they appear in the file.

Usage:
    from load_keys import load_av_keys
    keys = load_av_keys()           # reads keys.env by default
    keys = load_av_keys("keys.env") # explicit path
"""
from __future__ import annotations

import re
from pathlib import Path

_DEFAULT_KEYS_FILE = Path(__file__).parent / "keys.env"

# Matches AV_KEY or AV_KEYS or AV_KEY_<n>
_KEY_PATTERN = re.compile(
    r"^\s*AV_KEYS?\s*(?:_\d+)?\s*=\s*(.+?)\s*$",
    re.IGNORECASE,
)


def load_av_keys(path: str | Path = _DEFAULT_KEYS_FILE) -> list[str]:
    """Load Alpha Vantage API keys from a .env file.

    Args:
        path: Path to the keys file. Defaults to keys.env in project root.

    Returns:
        Ordered, deduplicated list of non-empty API key strings.

    Raises:
        FileNotFoundError: If the keys file does not exist.
        ValueError: If no keys are found in the file.
    """
    keys_path = Path(path).resolve()

    if not keys_path.exists():
        raise FileNotFoundError(
            f"Keys file not found: {keys_path}\n"
            "Create keys.env in the project root and add your keys.\n"
            "Example:\n"
            "  AV_KEYS=KEY1,KEY2,KEY3"
        )

    keys: list[str] = []
    seen: set[str] = set()

    with keys_path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()

            # Skip blank lines and comments
            if not line or line.startswith("#"):
                continue

            match = _KEY_PATTERN.match(line)
            if not match:
                continue

            value = match.group(1).strip()

            # Support comma-separated values on one line
            parts = [k.strip() for k in value.split(",")]
            for key in parts:
                if key and key not in seen:
                    keys.append(key)
                    seen.add(key)

    if not keys:
        raise ValueError(
            f"No API keys found in '{keys_path}'.\n"
            "Add keys in this format:\n"
            "  AV_KEYS=KEY1,KEY2,KEY3"
        )

    return keys


def print_key_summary(keys: list[str]) -> None:
    """Print a masked summary of loaded keys."""

    def mask(k: str) -> str:
        return f"{k[:4]}{'*' * max(0, len(k) - 8)}{k[-4:]}" if len(k) > 8 else k

    print(f"Loaded {len(keys)} Alpha Vantage key(s) from keys.env:")
    for i, k in enumerate(keys, start=1):
        print(f"  [{i}] {mask(k)}")


if __name__ == "__main__":
    # Quick test: print what keys are found
    try:
        keys = load_av_keys()
        print_key_summary(keys)
        print(f"\nTotal daily budget: {len(keys) * 25} requests/day")
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}")
