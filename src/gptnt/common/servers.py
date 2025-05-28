import socket

import httpx
from aiohttp import ClientSession
from httpx._client import AsyncClient
from httpx_aiohttp import AiohttpTransport

TimeoutTypes = float | httpx.Timeout | None

DEFAULT_CONNECTION_LIMITS = httpx.Limits(
    max_connections=None, max_keepalive_connections=None, keepalive_expiry=None
)


def httpx_create_async_client(
    base_url: str | httpx.URL, timeout: TimeoutTypes = 60
) -> AsyncClient:
    """Make shared client instance with httpx_aiohttp."""
    return httpx.AsyncClient(
        limits=DEFAULT_CONNECTION_LIMITS,
        timeout=timeout,
        base_url=base_url,
        transport=AiohttpTransport(client=lambda: ClientSession()),  # noqa: WPS506
    )


def get_available_port() -> int:
    """Return a random available port."""
    sock = socket.socket()
    sock.bind(("", 0))
    return sock.getsockname()[1]
