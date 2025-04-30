import pytest
from pydantic_ai import models
from pytest_cases import parametrize_with_cases

from gptnt.players.actions import InteractGameAction, InteractGameLocation, SetOfMarksLocation
from gptnt.players.ai.ai_player import AIPlayer
from gptnt.players.ai.defuser import DefuserOutputT
from gptnt.players.ai.dummy import DummyDefuserModel
from gptnt.players.ai.expert import ExpertOutputT
from tests.players.fixtures import AIPlayerCases

OutputDataT = ExpertOutputT | DefuserOutputT[InteractGameLocation]

pytestmark = pytest.mark.asyncio
models.ALLOW_MODEL_REQUESTS = False


@parametrize_with_cases("player", cases=AIPlayerCases)
def test_provide_message_to_agent(player: AIPlayer[None, OutputDataT]) -> None:
    agent = player.agent

    message = "Test message"
    output = agent.run_sync(message)

    assert output


@parametrize_with_cases("player", cases=AIPlayerCases, glob="defuser_mdp_set_of_marks")
async def test_functional_model_does_not_crash(player: AIPlayer[None, OutputDataT]) -> None:
    for _ in range(30):
        with player.agent.override(model=DummyDefuserModel()):
            response = await player.send_request_to_agent()

            assert response
            assert isinstance(response, InteractGameAction[SetOfMarksLocation])
