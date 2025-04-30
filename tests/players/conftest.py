from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL.Image import Resampling
from pytest_mock import MockerFixture
from whenever import Instant

from gptnt.common.image_ops import load_observation_from_bytes
from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.state.bomb import BombState
from gptnt.players.metrics import PlayerEpisodeTracker


@pytest.fixture
def dialogue_space_client(mocker: MockerFixture) -> DialogueSpaceClient:
    client = mocker.AsyncMock(spec=DialogueSpaceClient)
    client.connect.return_value = None
    return client


@pytest.fixture(scope="session")
def images(fixture_path: Path) -> tuple[bytes, bytes]:
    """Fixture to provide a segmentation screenshot and a screenshot as numpy arrays."""
    segmentation_image_path = fixture_path.joinpath("segmentation1.png")
    screenshot_image_path = fixture_path.joinpath("screenshot1.png")

    segmentation_image = load_observation_from_bytes(segmentation_image_path.read_bytes())
    screenshot_image = load_observation_from_bytes(screenshot_image_path.read_bytes())

    # make the iamge smaller for testing
    segmentation_image = segmentation_image.resize((512, 512), resample=Resampling.NEAREST)
    screenshot_image = screenshot_image.resize((512, 512), resample=Resampling.NEAREST)

    screenshot_buffer = BytesIO()
    screenshot_image.save(screenshot_buffer, format="PNG")
    segmentation_buffer = BytesIO()
    segmentation_image.save(segmentation_buffer, format="PNG")
    return screenshot_buffer.getvalue(), segmentation_buffer.getvalue()


@pytest.fixture
def game_client(mocker: MockerFixture, images: tuple[bytes, bytes]) -> KtaneClient:
    base_url = "http://localhost:1"

    game_client = KtaneClient(client=httpx.AsyncClient(base_url=base_url))
    game_client.get_observation = mocker.AsyncMock()
    game_client.get_observation.return_value = images[0], images[1], images[0]
    game_client.get_state = mocker.AsyncMock()
    game_client.get_state.return_value = BombState.model_validate(
        {
            "seed": 1000,
            "maxStrikes": 3,
            "currentStrikes": 0,
            "isDetonated": False,
            "isSolved": False,
            "isLightOn": True,
            "timerModule": {
                "secondsRemaining": 290.366852,
                "onFront": True,
                "index": 0,
                "name": "Timer",
            },
            "widgets": [{"serialNumber": "D24DN6", "position": "left", "name": "SerialNumber"}],
            "modules": [
                {
                    "sequence": "boxes",
                    "currentFrequency": 505,
                    "correctFrequency": 535,
                    "isSolved": False,
                    "inFocus": False,
                    "onFront": False,
                    "index": 5,
                    "name": "Morse",
                }
            ],
            "strikes": [],
        }
    )

    return game_client


@pytest.fixture
def player_episode_tracker() -> PlayerEpisodeTracker:
    tracker = PlayerEpisodeTracker(wandb_init_kwargs={"project": "gptnt", "mode": "disabled"})
    tracker.start_time = Instant.now()
    return tracker
