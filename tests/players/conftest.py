import httpx
import pytest
from pytest_mock import MockerFixture
from whenever import Instant

from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.state.bomb import BombState
from gptnt.players.metrics import PlayerEpisodeTracker


@pytest.fixture
def dialogue_space_client(mocker: MockerFixture) -> DialogueSpaceClient:
    client = mocker.AsyncMock(spec=DialogueSpaceClient)
    client.connect.return_value = None
    return client


@pytest.fixture
def game_client(mocker: MockerFixture) -> KtaneClient:
    base_url = "http://localhost:1"

    game_client = KtaneClient(client=httpx.AsyncClient(base_url=base_url))
    game_client.get_observation = mocker.AsyncMock()
    game_client.get_observation.return_value = b"", b"", b""
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
