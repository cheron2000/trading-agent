"""
data.providers.tor_session
============================

TorProxySession — routes HTTP traffic through local Tor SOCKS5 proxy.

Provides IP rotation via Tor NEWNYM signal to bypass Yahoo Finance
rate limiting. Requires Tor daemon running on 127.0.0.1:9050.

Prerequisites:
    1. Tor daemon running locally (listens on port 9050)
    2. pip install requests[socks] stem

Python Version: 3.11+
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

# Default ports — Tor Browser uses 9150/9151, standalone tor daemon uses 9050/9051
_DEFAULT_SOCKS_PORT: int = 9150
_DEFAULT_CONTROL_PORT: int = 9151


class TorProxySession:
    """Routes requests through local Tor SOCKS5 proxy.

    Wraps a requests.Session with Tor proxy settings and provides
    rotate_ip() to request a new Tor circuit (new exit node = new IP).

    Usage::

        # Tor Browser (default)
        tor = TorProxySession()

        # Standalone tor daemon
        tor = TorProxySession(socks_port=9050, control_port=9051)

        print(tor.get_current_ip())   # shows Tor exit IP
        tor.rotate_ip()               # request new circuit
        print(tor.get_current_ip())   # different IP
    """

    def __init__(
        self,
        control_password: str = "",
        socks_port: int = _DEFAULT_SOCKS_PORT,
        control_port: int = _DEFAULT_CONTROL_PORT,
    ) -> None:
        """
        Args:
            control_password: Tor control port password.
                              Empty string if no password set in torrc.
            socks_port:       SOCKS5 proxy port.
                              9150 = Tor Browser (default).
                              9050 = standalone tor daemon.
            control_port:     Tor control port.
                              9151 = Tor Browser (default).
                              9051 = standalone tor daemon.

        Raises:
            ImportError: If requests[socks] is not installed.
        """
        try:
            import requests
        except ImportError as exc:
            raise ImportError(
                "requests[socks] is required for Tor support: "
                "pip install requests[socks]"
            ) from exc

        self._requests = requests
        self._password = control_password
        self._socks_port = socks_port
        self._control_port = control_port
        self._session = self._make_session()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def session(self):
        """Return the underlying requests.Session routed through Tor."""
        return self._session

    def rotate_ip(self) -> None:
        """Request a new Tor circuit — new exit node = new public IP.

        Tor enforces a minimum 10s cooldown between NEWNYM signals.
        Logs a warning if rotation fails (Tor not running, wrong password).
        """
        try:
            from stem import Signal
            from stem.control import Controller

            with Controller.from_port(port=self._control_port) as ctrl:
                ctrl.authenticate(password=self._password)
                ctrl.signal(Signal.NEWNYM)
            _log.info("Tor circuit rotated — new exit IP requested.")
        except ImportError:
            _log.warning("stem is required for IP rotation: pip install stem")
        except Exception:
            _log.warning(
                "Failed to rotate Tor circuit — is Tor running on port %d?",
                self._control_port,
                exc_info=True,
            )

    def get_current_ip(self) -> str | None:
        """Return current public IP as seen through Tor exit node.

        Returns:
            IP address string, or None if unreachable.
        """
        try:
            resp = self._session.get("https://api.ipify.org", timeout=10)
            return resp.text.strip()
        except Exception:
            _log.warning("Could not fetch current IP via Tor.", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _make_session(self):
        """Build a requests.Session with Tor SOCKS5 proxy configured."""
        proxy = f"socks5h://127.0.0.1:{self._socks_port}"
        session = self._requests.Session()
        session.proxies = {
            "http": proxy,
            "https": proxy,
        }
        return session
