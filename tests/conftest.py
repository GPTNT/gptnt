import socket
from pathlib import Path

import pytest


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


@pytest.fixture(scope="session")
def fixture_path() -> Path:
    """Fixture to provide a storage path."""
    path = Path("storage/fixtures")
    assert path.exists()
    assert path.is_dir()
    return path
