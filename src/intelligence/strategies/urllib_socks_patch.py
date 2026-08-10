"""
Patch urllib to support SOCKS proxies via PySocks.

This module should be imported once at startup if Tor proxy is enabled.
It registers SOCKS proxy handlers with urllib's default opener.
"""

import socket

import socks


def patch_urllib_for_socks():
    """Register SOCKS proxy support with urllib.

    After calling this, urllib.request will honor HTTP_PROXY/HTTPS_PROXY
    environment variables even when they use socks5h:// scheme.
    """
    # Save original socket.socket
    _orig_socket = socket.socket

    # Check if already patched
    if hasattr(socket.socket, "_socks_patched"):
        return

    # Mark as patched
    socket.socket._socks_patched = True  # type: ignore

    # Wrap socket creation to use SOCKS if proxy env vars are set
    def _create_socket(*args, **kwargs):
        import os

        proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
        if proxy and "socks5h://" in proxy:
            # Extract host:port from socks5h://127.0.0.1:9150
            proxy_addr = proxy.replace("socks5h://", "").replace("socks5://", "")
            if ":" in proxy_addr:
                host, port = proxy_addr.rsplit(":", 1)
                port = int(port)
            else:
                host = proxy_addr
                port = 1080

            sock = socks.socksocket(*args, **kwargs)
            sock.set_proxy(socks.SOCKS5, host, port, rdns=True)
            return sock
        else:
            return _orig_socket(*args, **kwargs)

    # Monkey-patch socket.socket
    socket.socket = _create_socket  # type: ignore
