import httpx
import pytest
from pytest_mock import MockerFixture

from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.ktane.client import KtaneClient


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
    game_client.get_observation.return_value = b""

    return game_client
