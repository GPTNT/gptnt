import socket

import httpx

TimeoutTypes = float | httpx.Timeout | None

DEFAULT_CONNECTION_LIMITS = httpx.Limits(
    max_connections=None, max_keepalive_connections=None, keepalive_expiry=None
)
# default timeout is 10 minutes
DEFAULT_TIMEOUT = httpx.Timeout(timeout=10 * 60, connect=5.0)


def httpx_create_async_client(base_url: str | httpx.URL) -> httpx.AsyncClient:
    """Make shared client instance with httpx_aiohttp."""
    return httpx.AsyncClient(
        limits=DEFAULT_CONNECTION_LIMITS, timeout=DEFAULT_TIMEOUT, base_url=base_url
    )


def get_available_port() -> int:
    """Return a random available port."""
    sock = socket.socket()
    sock.bind(("", 0))
    return sock.getsockname()[1]
