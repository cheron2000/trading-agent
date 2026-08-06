"""
intelligence.agent.groq_client
================================

GroqClient — ILLMClient adapter for the Groq inference API.

Uses Groq's free tier (Llama 3.1 8B or Mixtral 8x7B) for fast,
zero-cost trading decisions. Falls back gracefully on errors.

Free tier limits (as of 2024):
  - 30 requests / minute
  - 14,400 requests / day
  - 6 symbols × 60 cycles/hour = 360 req/hour = 6 req/min ✓

Get a free API key at: https://console.groq.com

Python Version: 3.11+
"""

from __future__ import annotations

import json
import logging
import time
from urllib.request import Request
from urllib.error import HTTPError, URLError
import urllib.request

_log = logging.getLogger(__name__)

# Available Groq models (free tier)
GROQ_MODELS = {
    "llama3-8b":   "llama-3.1-8b-instant",    # fastest, recommended
    "llama3-70b":  "llama-3.3-70b-versatile",  # smarter, slower
    "mixtral":     "mixtral-8x7b-32768",        # good reasoning
}

_DEFAULT_MODEL = "llama3-8b"
_GROQ_API_URL  = "https://api.groq.com/openai/v1/chat/completions"


class GroqClient:
    """Groq inference API client implementing ILLMClient protocol.

    Supports API key rotation to bypass rate limits when multiple keys provided.

    Usage::

        # Single key (backward compatible)
        client = GroqClient(api_key="your_groq_key")
        
        # Multiple keys (auto-rotation on 429)
        client = GroqClient(api_key=["key1", "key2", "key3"])
        
        response = client.complete("Analyze this market data...")
    """

    def __init__(
        self,
        api_key: str | list[str],
        model: str = _DEFAULT_MODEL,
        temperature: float = 0.1,
        max_tokens: int = 256,
        timeout: float = 10.0,
    ) -> None:
        """
        Args:
            api_key:     Groq API key(s). Pass a single string or list of strings.
                         When multiple keys provided, rotates on 429 rate limit.
            model:       Model alias — one of: llama3-8b, llama3-70b, mixtral.
                         Or pass a full model ID directly.
            temperature: Sampling temperature (0.0 = deterministic).
                         Low values give more consistent trading signals.
            max_tokens:  Max response tokens. 256 is enough for JSON decisions.
            timeout:     HTTP timeout in seconds.

        Raises:
            ValueError: If api_key is empty or contains no valid keys.
        """
        # Normalize to list
        if isinstance(api_key, str):
            keys = [api_key.strip()]
        else:
            keys = [k.strip() for k in api_key if k and k.strip()]
        
        if not keys:
            raise ValueError("api_key must not be empty.")

        self._api_keys = keys
        self._current_key_index = 0
        self._model = GROQ_MODELS.get(model, model)  # resolve alias or use as-is
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout

        _log.info(
            "GroqClient initialized — model: %s, keys: %d",
            self._model, len(self._api_keys)
        )

    # ------------------------------------------------------------------
    # ILLMClient protocol
    # ------------------------------------------------------------------

    @property
    def _api_key(self) -> str:
        """Get the current API key (for backward compatibility and rotation)."""
        return self._api_keys[self._current_key_index]

    def _rotate_key(self) -> bool:
        """Rotate to the next API key.
        
        Returns:
            True if rotated to a new key, False if all keys exhausted.
        """
        if len(self._api_keys) <= 1:
            return False
        
        old_index = self._current_key_index
        self._current_key_index = (self._current_key_index + 1) % len(self._api_keys)
        
        # Check if we've cycled through all keys
        if self._current_key_index != old_index:
            _log.info(
                "Rotated to API key %d/%d",
                self._current_key_index + 1,
                len(self._api_keys)
            )
            return True
        return False

    def complete(self, prompt: str) -> str:
        """Send a prompt to Groq and return the model's text response.

        Args:
            prompt: Full prompt string (built by PromptBuilder).

        Returns:
            Raw text response from the model.

        Raises:
            RuntimeError: If the API call fails after retries.
        """
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a quantitative trading assistant. "
                        "Always respond with valid JSON only. "
                        "No explanations, no markdown, no code blocks. "
                        "Just the raw JSON object."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "response_format": {"type": "json_object"},  # enforces JSON output
        }

        body = json.dumps(payload).encode("utf-8")
        
        # Track keys tried to avoid infinite loops
        keys_tried = 0
        max_keys_to_try = len(self._api_keys)
        
        for attempt in range(3):
            # Build request with current key
            req = Request(
                _GROQ_API_URL,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                    "User-Agent": "python-httpx/0.27.0",
                    "Accept": "application/json",
                },
                method="POST",
            )
            
            try:
                # Use a direct opener that bypasses any system proxy (Tor)
                direct_opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler({})  # empty = no proxy
                )
                with direct_opener.open(req, timeout=self._timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    content = data["choices"][0]["message"]["content"]
                    _log.debug("Groq response: %s", content[:120])
                    return content.strip()

            except HTTPError as exc:
                if exc.code == 429:
                    # Try rotating to next key first
                    if keys_tried < max_keys_to_try and self._rotate_key():
                        keys_tried += 1
                        _log.info(
                            "Rate limit hit — trying key %d/%d (attempt %d/3)",
                            self._current_key_index + 1,
                            len(self._api_keys),
                            attempt + 1
                        )
                        continue  # Retry immediately with new key
                    
                    # All keys exhausted, wait and retry
                    wait = 2.0 ** attempt * 10  # 10s, 20s, 40s
                    _log.warning(
                        "Groq rate limit (429) on all keys — waiting %.0fs (attempt %d/3)",
                        wait, attempt + 1,
                    )
                    time.sleep(wait)
                elif exc.code in (401, 403):
                    raise RuntimeError(
                        f"Groq API key invalid or unauthorized (HTTP {exc.code}). "
                        "Check your key at console.groq.com."
                    ) from exc
                else:
                    raise RuntimeError(
                        f"Groq API error HTTP {exc.code}: {exc.reason}"
                    ) from exc

            except URLError as exc:
                if attempt < 2:
                    _log.warning("Groq network error (attempt %d/3): %s", attempt + 1, exc)
                    time.sleep(2.0 ** attempt)
                else:
                    raise RuntimeError(
                        f"Groq API unreachable after 3 attempts: {exc}"
                    ) from exc

            except (KeyError, IndexError) as exc:
                raise RuntimeError(
                    f"Unexpected Groq response structure: {exc}"
                ) from exc

        raise RuntimeError("Groq API failed after 3 attempts.")
