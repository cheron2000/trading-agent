"""
data.providers.tor_session
============================

TorProxySession — routes HTTP traffic through a local Tor SOCKS5 proxy.

Provides IP rotation via Tor's NEWNYM signal to bypass Yahoo Finance
rate limiting.

Prerequisites (either one of these two setups):
    1a. Tor Browser running (uses SOCKS port 9150, control port 9151 -
        the defaults below), OR
    1b. Standalone `tor` daemon (apt install tor / brew install tor)
        running as a service - defaults to SOCKS port 9050, control
        port 9051. Pass socks_port=9050, control_port=9051 to
        TorProxySession() if using this setup instead.
    2. pip install requests[socks] stem

Python Version: 3.11+
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

# Defaults assume Tor Browser. For a standalone `tor` daemon, override
# with socks_port=9050, control_port=9051 (its standard defaults).
DEFAULT_SOCKS_PORT = 9150
DEFAULT_CONTROL_PORT = 9151


class TorProxySession:
    """Routes requests through a local Tor SOCKS5 proxy.

    Wraps a requests.Session with Tor proxy settings and provides
    rotate_ip() to request a new Tor circuit (new exit node = new IP).

    Usage::

        tor = TorProxySession()                                  # Tor Browser
        tor = TorProxySession(socks_port=9050, control_port=9051)  # tor daemon
        print(tor.get_current_ip())   # shows Tor exit IP
        tor.rotate_ip()               # request new circuit
        print(tor.get_current_ip())   # different IP
    """

    def __init__(
        self,
        control_password: str = "",
        socks_port: int = DEFAULT_SOCKS_PORT,
        control_port: int = DEFAULT_CONTROL_PORT,
    ) -> None:
        """
        Args:
            control_password: Tor control port password.
                              Empty string if no password set in torrc.
            socks_port: Tor's SOCKS5 proxy port. Defaults to Tor
                        Browser's port (9150); use 9050 for a
                        standalone `tor` daemon.
            control_port: Tor's control port (for IP rotation).
                          Defaults to Tor Browser's port (9151); use
                          9051 for a standalone `tor` daemon.

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

    def rotate_ip(self) -> bool:
        """Request a new Tor circuit — new exit node = new public IP.

        Tor enforces a minimum 10s cooldown between NEWNYM signals.

        Returns:
            True if the rotation signal was sent successfully, False
            if it failed (Tor not running, wrong password, stem not
            installed). Callers that rely on rotation to dodge rate
            limiting should check this rather than assuming it always
            works - a warning is logged either way, but a caller
            retrying in a loop needs the return value to know whether
            to keep trying rotation or fall back to something else.
        """
        try:
            from stem import Signal
            from stem.control import Controller

            with Controller.from_port(port=self._control_port) as ctrl:
                ctrl.authenticate(password=self._password)
                ctrl.signal(Signal.NEWNYM)
            _log.info("Tor circuit rotated — new exit IP requested.")
            return True
        except ImportError:
            _log.warning("stem is required for IP rotation: pip install stem")
            return False
        except Exception:  # noqa: BLE001 -- stem errors vary; logged
            _log.warning(
                "Failed to rotate Tor circuit — is Tor running on port %d?",
                self._control_port,
                exc_info=True,
            )
            return False

    def get_current_ip(self) -> str | None:
        """Return current public IP as seen through Tor exit node.

        Returns:
            IP address string, or None if unreachable.
        """
        try:
            resp = self._session.get("https://api.ipify.org", timeout=10)
            return resp.text.strip()
        except Exception:  # noqa: BLE001 -- external call; logged
            _log.warning("Could not fetch current IP via Tor.", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _make_session(self):
        """Build a requests.Session with Tor SOCKS5 proxy configured."""
        session = self._requests.Session()
        proxy_url = f"socks5h://127.0.0.1:{self._socks_port}"
        session.proxies = {
            "http": proxy_url,
            "https": proxy_url,
        }
        return session
