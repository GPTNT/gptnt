from pytest_cases import parametrize_with_cases

from gptnt.players.actions import InteractGameLocation
from gptnt.players.ai.ai_player import AIPlayer
from gptnt.players.ai.defuser import DefuserOutputT
from gptnt.players.ai.expert import ExpertOutputT
from tests.players.fixtures import AIPlayerCases

OutputDataT = ExpertOutputT | DefuserOutputT[InteractGameLocation]


@parametrize_with_cases("player", cases=AIPlayerCases)
def test_provide_message_to_agent(player: AIPlayer[None, OutputDataT]) -> None:
    agent = player.agent

    message = "Test message"
    output = agent.run_sync(message)

    assert output
