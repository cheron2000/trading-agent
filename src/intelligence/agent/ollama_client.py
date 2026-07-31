"""
intelligence.agent.ollama_client
=================================

OllamaClient — a real ILLMClient implementation backed by a local
Ollama server, for use with LLMAgent (see llm_agent.py).

Requires the Ollama server to already be running and the target
model already pulled — see scripts/setup_local_llm.sh, which installs
Ollama, starts the server, and pulls the default model.

Python Version: 3.11+
"""

from __future__ import annotations

import requests


class OllamaClient:
    """ILLMClient implementation that calls a local Ollama server.

    Satisfies the same `complete(prompt) -> str` protocol LLMAgent
    expects, so it can be dropped in wherever a mock client is used
    today, e.g.:

        client = OllamaClient(model="qwen2.5:1.5b")
        agent = LLMAgent(llm_client=client, ...)

    Deliberately fails loud rather than silently: if the server is
    unreachable, times out, or returns something unexpected, this
    raises rather than returning a default/empty string that could
    get parsed by LLMAgent as a spurious decision.
    """

    def __init__(
        self,
        model: str = "qwen2.5:1.5b",
        host: str = "http://localhost:11434",
        timeout_seconds: float = 30.0,
        temperature: float = 0.2,
    ) -> None:
        """
        Args:
            model:           Ollama model tag (must already be pulled).
            host:             Base URL of the Ollama server.
            timeout_seconds: Request timeout — trading decisions are
                              time-sensitive, so this should stay short
                              rather than letting a slow local model
                              stall the whole decision cycle.
            temperature:      Lower values (default 0.2) favor
                               consistent, less erratic trading
                               decisions over creative variety.

        Raises:
            ValueError: If model/host are empty or timeout/temperature
                        are out of a sane range.
        """
        if not model or not model.strip():
            raise ValueError("model must not be empty.")
        if not host or not host.strip():
            raise ValueError("host must not be empty.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if not (0.0 <= temperature <= 2.0):
            raise ValueError("temperature must be in [0, 2].")

        self._model = model
        self._host = host.rstrip("/")
        self._timeout = timeout_seconds
        self._temperature = temperature

    def complete(self, prompt: str) -> str:
        """Send a prompt to the local Ollama server and return the response.

        Args:
            prompt: The full prompt text (LLMAgent/PromptBuilder already
                    assembles context + instructions into this string).

        Returns:
            The model's raw text response (LLMAgent is responsible for
            JSON-parsing and validating it).

        Raises:
            ConnectionError: If the Ollama server is unreachable (e.g.
                              not started — run scripts/setup_local_llm.sh).
            TimeoutError:     If the model doesn't respond within
                              timeout_seconds.
            ValueError:       If the server response is malformed.
        """
        if not prompt or not prompt.strip():
            raise ValueError("prompt must not be empty.")

        try:
            resp = requests.post(
                f"{self._host}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": self._temperature},
                },
                timeout=self._timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise TimeoutError(
                f"Ollama did not respond within {self._timeout}s "
                f"(model={self._model})."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise ConnectionError(
                f"Could not reach Ollama at {self._host}. "
                f"Is it running? Try: ./scripts/setup_local_llm.sh"
            ) from exc

        if resp.status_code != 200:
            raise ValueError(
                f"Ollama returned HTTP {resp.status_code}: {resp.text[:500]}"
            )

        try:
            data = resp.json()
            text = data["response"]
        except (ValueError, KeyError) as exc:
            raise ValueError(
                f"Unexpected Ollama response shape: {resp.text[:500]}"
            ) from exc

        if not isinstance(text, str):
            raise TypeError(f"Expected string response, got {type(text)}.")

        return text
