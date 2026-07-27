"""
Tests for data.providers.tor_session.TorProxySession.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from data.providers.tor_session import (
    DEFAULT_CONTROL_PORT,
    DEFAULT_SOCKS_PORT,
    TorProxySession,
)


class TestTorProxySessionConfiguration:
    def test_defaults_match_tor_browser_ports(self) -> None:
        tor = TorProxySession()
        assert tor._socks_port == DEFAULT_SOCKS_PORT == 9150
        assert tor._control_port == DEFAULT_CONTROL_PORT == 9151

    def test_session_proxies_use_configured_socks_port(self) -> None:
        tor = TorProxySession(socks_port=9050)
        assert tor.session.proxies["https"] == "socks5h://127.0.0.1:9050"

    def test_custom_ports_for_standalone_tor_daemon(self) -> None:
        tor = TorProxySession(socks_port=9050, control_port=9051)
        assert tor._socks_port == 9050
        assert tor._control_port == 9051


class TestRotateIpReturnValue:
    def test_rotate_ip_returns_true_on_success(self) -> None:
        tor = TorProxySession()
        mock_controller = MagicMock()
        mock_controller.__enter__ = MagicMock(return_value=mock_controller)
        mock_controller.__exit__ = MagicMock(return_value=False)

        with patch("stem.control.Controller.from_port", return_value=mock_controller):
            assert tor.rotate_ip() is True

    def test_rotate_ip_returns_false_when_stem_missing(self) -> None:
        tor = TorProxySession()
        with patch.dict("sys.modules", {"stem": None, "stem.control": None}):
            assert tor.rotate_ip() is False

    def test_rotate_ip_returns_false_on_connection_failure(self) -> None:
        tor = TorProxySession()
        with patch(
            "stem.control.Controller.from_port",
            side_effect=OSError("connection refused"),
        ):
            assert tor.rotate_ip() is False

    def test_rotate_ip_uses_configured_control_port(self) -> None:
        tor = TorProxySession(control_port=9051)
        with patch("stem.control.Controller.from_port") as mock_from_port:
            mock_ctrl = MagicMock()
            mock_from_port.return_value.__enter__ = MagicMock(return_value=mock_ctrl)
            mock_from_port.return_value.__exit__ = MagicMock(return_value=False)
            tor.rotate_ip()
            mock_from_port.assert_called_once_with(port=9051)


class TestGetCurrentIp:
    def test_returns_none_on_failure(self) -> None:
        tor = TorProxySession()
        with patch.object(tor.session, "get", side_effect=Exception("no route")):
            assert tor.get_current_ip() is None

    def test_returns_stripped_ip_on_success(self) -> None:
        tor = TorProxySession()
        mock_resp = MagicMock()
        mock_resp.text = "1.2.3.4\n"
        with patch.object(tor.session, "get", return_value=mock_resp):
            assert tor.get_current_ip() == "1.2.3.4"
