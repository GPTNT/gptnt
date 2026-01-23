import os
import socket
from pathlib import Path

import httpx
import pytest
from pytest_cases import fixture, param_fixture
from pytest_mock import MockerFixture

from gptnt.common.paths import Paths
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.manual import KtaneManualPaths
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol
from gptnt.prompts.prompt_cache import PromptCache

# disable Weave and WandB for testing
os.environ["WEAVE_DISABLED"] = "true"
os.environ["WANDB_MODE"] = "disabled"


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


# ============================================================================
# Fixtures & Cases
# ============================================================================

interaction_location_method = param_fixture(
    "interaction_location_method", ["set-of-marks", "coordinates"]
)
structured_output_mode = param_fixture("structured_output_mode", ["prompted"])


@fixture
def capabilities(
    interaction_location_method: str, structured_output_mode: str
) -> PlayerCapabilities:
    """Fixture for PlayerCapabilities with varying interaction location methods."""
    return PlayerCapabilities(
        player_name="test_player",
        player_type="ai",
        use_structured_outputs=True,
        structured_output_mode=structured_output_mode,
        max_observation_window_length=16,
        interaction_location_method=interaction_location_method,
    )


class ProtocolCases:
    """Case class for different PlayerProtocol configurations."""

    def case_collaborative(self) -> PlayerProtocol:
        """Collaborative protocol (is_playing_alone=False, allows SendMessage)."""
        return PlayerProtocol(
            role="defuser",
            communication_style="sync",
            is_playing_alone=False,
            include_manual=True,
            receive_feedback_after_action=False,
            allow_magic_actions=False,
        )

    def case_solo(self) -> PlayerProtocol:
        """Solo protocol (is_playing_alone=True, no SendMessage)."""
        return PlayerProtocol(
            role="defuser",
            communication_style="sync",
            is_playing_alone=True,
            include_manual=True,
            receive_feedback_after_action=False,
            allow_magic_actions=False,
        )
