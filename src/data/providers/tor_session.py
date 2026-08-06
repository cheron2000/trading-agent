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

SOCKS5_PROXY = "socks5h://127.0.0.1:9150"  # Tor Browser default SOCKS port
TOR_CONTROL_PORT = 9151  # Tor Browser control port


class TorProxySession:
    """Routes requests through local Tor SOCKS5 proxy.

    Wraps a requests.Session with Tor proxy settings and provides
    rotate_ip() to request a new Tor circuit (new exit node = new IP).

    Usage::

        tor = TorProxySession()
        print(tor.get_current_ip())   # shows Tor exit IP
        tor.rotate_ip()               # request new circuit
        print(tor.get_current_ip())   # different IP
    """

    def __init__(self, control_password: str = "") -> None:
        """
        Args:
            control_password: Tor control port password.
                              Empty string if no password set in torrc.

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

            with Controller.from_port(port=TOR_CONTROL_PORT) as ctrl:
                ctrl.authenticate(password=self._password)
                ctrl.signal(Signal.NEWNYM)
            _log.info("Tor circuit rotated — new exit IP requested.")
        except ImportError:
            _log.warning("stem is required for IP rotation: pip install stem")
        except Exception:
            _log.warning(
                "Failed to rotate Tor circuit — is Tor running on port %d?",
                TOR_CONTROL_PORT,
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
        session = self._requests.Session()
        session.proxies = {
            "http": SOCKS5_PROXY,
            "https": SOCKS5_PROXY,
        }
        return session
