import os
from pathlib import Path

import httpx
import pytest
from pytest_factoryboy import register
from pytest_mock import MockerFixture

from gptnt.common.paths import Paths
from gptnt.common.servers import get_available_port
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.manual import KtaneManualPaths
from gptnt.prompts.prompt_cache import PromptCache

from tests._factories.players import PlayerProtocolFactory

# Import all the fixtures from every file in the tests/_cases dir.
pytest_plugins = [
    fixture_file.as_posix().replace("/", ".").replace(".py", "")
    for fixture_file in Path().rglob("tests/_cases/[!__]*.py")
]

# Register factories with pytest-factoryboy
_ = register(PlayerProtocolFactory)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def host() -> str:
    """Get the host."""
    return "localhost"


@pytest.fixture
def port() -> int:
    """Return a random available port."""
    return get_available_port()


@pytest.fixture(scope="session")
def fixture_path() -> Path:
    """Fixture to provide a storage path."""
    path = Path("storage/fixtures")
    assert path.exists()
    assert path.is_dir()
    return path


@pytest.fixture
async def ktane_client(host: str, port: int, mocker: MockerFixture) -> KtaneClient:
    """Provides an instance of the Ktane Client for testing."""
    ktane_client = KtaneClient(url=f"http://{host}:{port}")
    type(ktane_client)._client = mocker.PropertyMock(
        return_value=httpx.AsyncClient(base_url=f"http://{host}:{port}")
    )
    return ktane_client


@pytest.fixture(scope="session", autouse=True)
def prompt_cache() -> None:
    """Fixture to set up the prompt cache before running tests."""
    paths = Paths()
    ktane_manual = KtaneManualPaths()
    PromptCache.initialise(paths.prompts, ktane_manual.text_dir, ktane_manual.images_small_dir)


@pytest.fixture(scope="session", autouse=True)
def disable_wandb_and_weave() -> None:
    """Fixture to disable Weave and WandB for testing."""
    os.environ["WEAVE_DISABLED"] = "true"
    os.environ["WANDB_MODE"] = "disabled"
