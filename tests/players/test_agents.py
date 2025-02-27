from pytest_cases import parametrize_with_cases

from gptnt.players.expert import ExpertResultType
from gptnt.players.player import Player
from tests.players.fixtures import PlayerCases

ResultDataT = ExpertResultType


@parametrize_with_cases("player", cases=PlayerCases)
def test_provide_message_to_agent(player: Player[None, ResultDataT]) -> None:
    agent = player.agent

    message = "Test message"
    output = agent.run_sync(message)

    # Make sure the result type is one of the expected types
    assert isinstance(output.data, agent.result_type)
