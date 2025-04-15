from pytest_cases import parametrize_with_cases

from gptnt.players.actions import InteractGameLocation
from gptnt.players.ai.ai_player import AIPlayer
from gptnt.players.ai.defuser import DefuserResultT
from gptnt.players.ai.expert import ExpertResultT
from tests.players.fixtures import AIPlayerCases

ResultDataT = ExpertResultT | DefuserResultT[InteractGameLocation]


@parametrize_with_cases("player", cases=AIPlayerCases)
def test_provide_message_to_agent(player: AIPlayer[None, ResultDataT]) -> None:
    agent = player.agent

    message = "Test message"
    output = agent.run_sync(message)

    assert output
