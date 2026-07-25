"""
load_keys.py — API key loader for the AI Trading OS.

Reads keys.env and returns the list of Alpha Vantage API keys,
and the Groq API key for LLM trading decisions.

Supports two formats in the same file:

    AV_KEYS=KEY1,KEY2,KEY3          # comma-separated list
    AV_KEY_1=ABCD1234EFGH5678       # individual numbered keys
    AV_KEY_2=WXYZ9876MNOP4321
    GROQ_API_KEY=gsk_xxxxxxxxxxxx   # Groq key for LLM
    GROQ_MODEL=llama3-8b            # optional model override
    TELEGRAM_BOT_TOKEN=123:ABC      # Telegram bot token
    TELEGRAM_CHAT_ID=987654321      # Telegram chat ID
    ALPACA_API_KEY=PKXXXXXXXX       # Alpaca API key
    ALPACA_SECRET_KEY=xxxxxxxx      # Alpaca secret key

Usage:
    from load_keys import load_av_keys, load_groq_key
    keys = load_av_keys()
    groq_key, groq_model = load_groq_key()
    bot_token, chat_id = load_telegram_keys()
    api_key, secret_key = load_alpaca_keys()
"""
from __future__ import annotations

import re
from pathlib import Path

_DEFAULT_KEYS_FILE = Path(__file__).parent / "keys.env"

# Matches AV_KEY or AV_KEYS or AV_KEY_<n>
_AV_KEY_PATTERN = re.compile(
    r"^\s*AV_KEYS?\s*(?:_\d+)?\s*=\s*(.+?)\s*$",
    re.IGNORECASE,
)
# Matches GROQ_API_KEY
_GROQ_KEY_PATTERN = re.compile(
    r"^\s*GROQ_API_KEY\s*=\s*(.+?)\s*$",
    re.IGNORECASE,
)
# Matches GROQ_MODEL
_GROQ_MODEL_PATTERN = re.compile(
    r"^\s*GROQ_MODEL\s*=\s*(.+?)\s*$",
    re.IGNORECASE,
)
# Matches FINNHUB_API_KEY
_FINNHUB_KEY_PATTERN = re.compile(
    r"^\s*FINNHUB_API_KEY\s*=\s*(.+?)\s*$",
    re.IGNORECASE,
)
# Matches TELEGRAM_BOT_TOKEN
_TELEGRAM_BOT_TOKEN_PATTERN = re.compile(
    r"^\s*TELEGRAM_BOT_TOKEN\s*=\s*(.+?)\s*$",
    re.IGNORECASE,
)
# Matches TELEGRAM_CHAT_ID
_TELEGRAM_CHAT_ID_PATTERN = re.compile(
    r"^\s*TELEGRAM_CHAT_ID\s*=\s*(.+?)\s*$",
    re.IGNORECASE,
)
# Matches ALPACA_API_KEY
_ALPACA_API_KEY_PATTERN = re.compile(
    r"^\s*ALPACA_API_KEY\s*=\s*(.+?)\s*$",
    re.IGNORECASE,
)
# Matches ALPACA_SECRET_KEY
_ALPACA_SECRET_KEY_PATTERN = re.compile(
    r"^\s*ALPACA_SECRET_KEY\s*=\s*(.+?)\s*$",
    re.IGNORECASE,
)


def load_av_keys(path: str | Path = _DEFAULT_KEYS_FILE) -> list[str]:
    """Load Alpha Vantage API keys from a .env file."""
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
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = _AV_KEY_PATTERN.match(line)
            if not match:
                continue
            value = match.group(1).strip()
            for key in [k.strip() for k in value.split(",")]:
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


def load_groq_key(path: str | Path = _DEFAULT_KEYS_FILE) -> tuple[str | None, str]:
    """Load Groq API key and model from keys.env.

    Returns:
        Tuple of (api_key, model_name).
        api_key is None if not set or empty.
        model_name defaults to 'llama3-8b'.
    """
    keys_path = Path(path).resolve()
    api_key: str | None = None
    model: str = "llama3-8b"

    if not keys_path.exists():
        return None, model

    with keys_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _GROQ_KEY_PATTERN.match(line)
            if m:
                val = m.group(1).strip()
                if val:
                    api_key = val
            m2 = _GROQ_MODEL_PATTERN.match(line)
            if m2:
                val2 = m2.group(1).strip()
                if val2:
                    model = val2

    return api_key, model


def load_finnhub_key(path: str | Path = _DEFAULT_KEYS_FILE) -> str | None:
    """Load Finnhub API key from keys.env.

    Returns:
        API key string, or None if not set.
    """
    keys_path = Path(path).resolve()
    if not keys_path.exists():
        return None
    with keys_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _FINNHUB_KEY_PATTERN.match(line)
            if m:
                val = m.group(1).strip()
                if val:
                    return val
    return None


def load_telegram_keys(path: str | Path = _DEFAULT_KEYS_FILE) -> tuple[str, str]:
    """Load Telegram bot credentials from keys.env.

    Returns:
        Tuple of (bot_token, chat_id).

    Raises:
        FileNotFoundError: If the keys file does not exist.
        ValueError: If either TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is
            absent from the file or is present but empty/whitespace.
    """
    keys_path = Path(path).resolve()

    if not keys_path.exists():
        raise FileNotFoundError(
            f"Keys file not found: {keys_path}\n"
            "Create keys.env in the project root and add your Telegram credentials.\n"
            "Example:\n"
            "  TELEGRAM_BOT_TOKEN=123456789:ABCDEFabcdef\n"
            "  TELEGRAM_CHAT_ID=987654321"
        )

    bot_token: str | None = None
    chat_id: str | None = None

    with keys_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _TELEGRAM_BOT_TOKEN_PATTERN.match(line)
            if m:
                val = m.group(1).strip()
                if val:
                    bot_token = val
            m2 = _TELEGRAM_CHAT_ID_PATTERN.match(line)
            if m2:
                val2 = m2.group(1).strip()
                if val2:
                    chat_id = val2

    missing: list[str] = []
    if not bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not chat_id:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        raise ValueError(
            f"The following Telegram key(s) are missing or empty in '{keys_path}': "
            + ", ".join(missing)
        )

    return bot_token, chat_id  # type: ignore[return-value]  # guarded by missing check


def load_alpaca_keys(path: str | Path = _DEFAULT_KEYS_FILE) -> tuple[str, str]:
    """Load Alpaca broker credentials from keys.env.

    Returns:
        Tuple of (api_key, secret_key).

    Raises:
        FileNotFoundError: If the keys file does not exist.
        ValueError: If either ALPACA_API_KEY or ALPACA_SECRET_KEY is
            absent from the file or is present but empty/whitespace.
    """
    keys_path = Path(path).resolve()

    if not keys_path.exists():
        raise FileNotFoundError(
            f"Keys file not found: {keys_path}\n"
            "Create keys.env in the project root and add your Alpaca credentials.\n"
            "Example:\n"
            "  ALPACA_API_KEY=PKXXXXXXXXXXXXXXXX\n"
            "  ALPACA_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        )

    api_key: str | None = None
    secret_key: str | None = None

    with keys_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _ALPACA_API_KEY_PATTERN.match(line)
            if m:
                val = m.group(1).strip()
                if val:
                    api_key = val
            m2 = _ALPACA_SECRET_KEY_PATTERN.match(line)
            if m2:
                val2 = m2.group(1).strip()
                if val2:
                    secret_key = val2

    missing: list[str] = []
    if not api_key:
        missing.append("ALPACA_API_KEY")
    if not secret_key:
        missing.append("ALPACA_SECRET_KEY")
    if missing:
        raise ValueError(
            f"The following Alpaca key(s) are missing or empty in '{keys_path}': "
            + ", ".join(missing)
        )

    return api_key, secret_key  # type: ignore[return-value]  # guarded by missing check


def print_key_summary(keys: list[str]) -> None:
    """Print a masked summary of loaded keys."""

    def mask(k: str) -> str:
        return f"{k[:4]}{'*' * max(0, len(k) - 8)}{k[-4:]}" if len(k) > 8 else k

    print(f"Loaded {len(keys)} Alpha Vantage key(s) from keys.env:")
    for i, k in enumerate(keys, start=1):
        print(f"  [{i}] {mask(k)}")


if __name__ == "__main__":
    try:
        keys = load_av_keys()
        print_key_summary(keys)
        print(f"\nTotal AV daily budget: {len(keys) * 25} requests/day")
    except (FileNotFoundError, ValueError) as exc:
        print(f"AV keys error: {exc}")

    groq_key, groq_model = load_groq_key()
    if groq_key:
        masked = f"{groq_key[:8]}{'*' * max(0, len(groq_key)-12)}{groq_key[-4:]}"
        print(f"\nGroq API key loaded: {masked}")
        print(f"Groq model:          {groq_model}")
        print("LLM decisions:       ENABLED")
    else:
        print("\nGroq API key:        NOT SET")
        print("LLM decisions:       DISABLED (using SimpleRuleStrategy)")
        print("→ Add GROQ_API_KEY=your_key to keys.env")
