"""
Tests for intelligence.agent.ollama_client.OllamaClient.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from intelligence.agent.ollama_client import OllamaClient


class TestOllamaClientConstruction:
    def test_default_construction(self) -> None:
        client = OllamaClient()
        assert client._model == "qwen2.5:1.5b"

    def test_strips_trailing_slash_from_host(self) -> None:
        client = OllamaClient(host="http://localhost:11434/")
        assert client._host == "http://localhost:11434"

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"model": ""},
            {"model": "   "},
            {"host": ""},
            {"timeout_seconds": 0},
            {"timeout_seconds": -1},
            {"temperature": -0.1},
            {"temperature": 2.1},
        ],
    )
    def test_rejects_invalid_construction(self, kwargs: dict) -> None:
        with pytest.raises(ValueError):
            OllamaClient(**kwargs)


class TestOllamaClientComplete:
    def test_rejects_empty_prompt(self) -> None:
        client = OllamaClient()
        with pytest.raises(ValueError):
            client.complete("")

    @patch("intelligence.agent.ollama_client.requests.post")
    def test_success_returns_response_text(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "response": '{"action": "HOLD", "confidence": 0.5, "rationale": "flat"}'
            },
        )
        client = OllamaClient()
        result = client.complete("some prompt")
        assert "HOLD" in result
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["model"] == "qwen2.5:1.5b"
        assert kwargs["json"]["prompt"] == "some prompt"
        assert kwargs["json"]["stream"] is False

    @patch("intelligence.agent.ollama_client.requests.post")
    def test_timeout_raises_timeout_error(self, mock_post: MagicMock) -> None:
        mock_post.side_effect = requests.exceptions.Timeout()
        client = OllamaClient()
        with pytest.raises(TimeoutError):
            client.complete("prompt")

    @patch("intelligence.agent.ollama_client.requests.post")
    def test_connection_error_raises_connection_error(
        self, mock_post: MagicMock
    ) -> None:
        mock_post.side_effect = requests.exceptions.ConnectionError()
        client = OllamaClient()
        with pytest.raises(ConnectionError):
            client.complete("prompt")

    @patch("intelligence.agent.ollama_client.requests.post")
    def test_non_200_status_raises_value_error(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=500, text="server error")
        client = OllamaClient()
        with pytest.raises(ValueError, match="500"):
            client.complete("prompt")

    @patch("intelligence.agent.ollama_client.requests.post")
    def test_malformed_json_raises_value_error(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"unexpected": "shape"},
            text='{"unexpected": "shape"}',
        )
        client = OllamaClient()
        with pytest.raises(ValueError, match="Unexpected Ollama response"):
            client.complete("prompt")

    @patch("intelligence.agent.ollama_client.requests.post")
    def test_non_string_response_raises_type_error(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"response": 12345}
        )
        client = OllamaClient()
        with pytest.raises(TypeError, match="Expected string response"):
            client.complete("prompt")
