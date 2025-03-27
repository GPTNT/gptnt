import socket

import pytest

from gptnt.common.logger import configure_logging

configure_logging()


@pytest.fixture
def host() -> str:
    """Get the host."""
    return "localhost"


@pytest.fixture
def port() -> int:
    """Return a random available port."""
    sock = socket.socket()
    sock.bind(("", 0))
    port = sock.getsockname()[1]
    return port
