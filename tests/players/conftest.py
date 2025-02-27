import pytest
from pytest_mock import MockerFixture

from gptnt.dialogue_space.client import DialogueSpaceClient


@pytest.fixture
def dialogue_space_client(mocker: MockerFixture) -> DialogueSpaceClient:
    client = mocker.AsyncMock(spec=DialogueSpaceClient)
    client.connect.return_value = None
    return client
