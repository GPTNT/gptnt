import os
import socket
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from pytest_mock import MockerFixture

from gptnt.ktane.client import KtaneClient

os.environ["WEAVE_DISABLED"] = "true"


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


@pytest_asyncio.fixture
async def ktane_client(host: str, port: int, mocker: MockerFixture) -> KtaneClient:
    """Provides an instance of the Ktane Client for testing."""
    ktane_client = KtaneClient(url=f"http://{host}:{port}")
    type(ktane_client).client = mocker.PropertyMock(  # pyright: ignore[reportAttributeAccessIssue]
        return_value=httpx.AsyncClient(base_url=f"http://{host}:{port}")
    )
    return ktane_client
