import socket

from pydantic import BaseModel


def get_available_port() -> int:
    """Return a random available port."""
    sock = socket.socket()
    sock.bind(("", 0))
    return sock.getsockname()[1]


class ClientMetadata(BaseModel):
    """Metadata for a given client."""

    fastapi_url: str | None = None
    """The URL of the FastAPI server that it's running on."""
