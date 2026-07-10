import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from pytest_factoryboy import register

from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths
from gptnt.common.servers import get_available_port
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.manual import KtaneManualPaths
from gptnt.prompts.prompt_cache import PromptCache

from tests._factories.players import PlayerProtocolFactory

configure_logging(enable_logfire=False)


@pytest.fixture(autouse=True)
def configure_test_environment(tmp_path: Path) -> None:
    """Point the experiment recorder at a throwaway per-test dir.

    The fast-poll service timeouts are set at conftest import time (see top of this module) — they
    MUST be in place before `gptnt.interactive` is imported, which is too early for a fixture.
    """
    records_dir = tmp_path.joinpath("output")
    records_dir.mkdir(parents=True, exist_ok=True)
    _ = os.environ.setdefault("EXPERIMENT_RECORDER_OUTPUTS", records_dir.as_posix())


# Import all the fixtures from every file in the tests/_cases dir. Anchor the glob to this file's
# directory, not the CWD: a bare rglob from the working tree also sweeps up nested git worktrees
# (e.g. .claude/worktrees/*/tests/_cases), which produce unimportable plugin names.
pytest_plugins = [
    f"tests._cases.{fixture_file.stem}"
    for fixture_file in (Path(__file__).parent / "_cases").glob("[!__]*.py")
]


# Register factories with pytest-factoryboy
_ = register(PlayerProtocolFactory)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def host() -> str:
    """Get the host."""
    return "127.0.0.1"


@pytest.fixture
def port() -> int:
    """Return a random available port."""
    return get_available_port()


@pytest.fixture(scope="session")
def fixture_path() -> Path:
    """Provide the test-fixture data dir."""
    path = Path(__file__).parent / "_data"
    assert path.exists()
    assert path.is_dir()
    return path


@pytest.fixture
async def ktane_client(host: str, port: int) -> AsyncIterator[KtaneClient]:
    """Provides an instance of the Ktane Client for testing.

    `KtaneClient.__post_init__` already builds a real `httpx.AsyncClient` bound to this loop, so we
    just hand it back and close it on teardown. (We must NOT patch `_client` onto the *class* — a
    `PropertyMock` assigned to the class is a descriptor that leaks into every other test's
    `KtaneClient` instances and breaks them on a closed event loop.)
    """
    client = KtaneClient(url=f"http://{host}:{port}")
    yield client
    await client.client.aclose()


@pytest.fixture(scope="session", autouse=True)
def prompt_cache() -> None:
    """Fixture to set up the prompt cache before running tests."""
    paths = Paths()
    ktane_manual = KtaneManualPaths()
    PromptCache.initialise(paths.prompts, ktane_manual.text_dir, ktane_manual.images_small_dir)
