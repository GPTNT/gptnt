from pytest_cases import parametrize_with_cases

from gptnt.players.actions import InteractGameLocation
from gptnt.players.defuser import DefuserResultT
from gptnt.players.expert import ExpertResultT
from gptnt.players.player import Player
from tests.players.fixtures import PlayerCases

ResultDataT = ExpertResultT | DefuserResultT[InteractGameLocation]


@parametrize_with_cases("player", cases=PlayerCases)
def test_provide_message_to_agent(player: Player[None, ResultDataT]) -> None:
    agent = player.agent

    message = "Test message"
    output = agent.run_sync(message)

    assert output
