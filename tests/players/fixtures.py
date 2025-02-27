import pytest
from pydantic_ai import Agent
from pytest_mock import MockerFixture

from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.players.expert import ExpertPlayer, ExpertResultType


class PlayerCases:
    """Parametrize fixtures for players."""

    def case_expert_player(self, dialogue_space_client: DialogueSpaceClient) -> ExpertPlayer:
        expert_agent = Agent[None, ExpertResultType]("test", result_type=ExpertResultType)
        return ExpertPlayer(agent=expert_agent, dialogue_space_client=dialogue_space_client)


@pytest.fixture
def dialogue_space_client(mocker: MockerFixture) -> DialogueSpaceClient:
    client = mocker.AsyncMock(spec=DialogueSpaceClient)
    client.connect.return_value = None
    return client
