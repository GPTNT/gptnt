from pydantic_ai import Agent

from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.ktane.client import KtaneClient
from gptnt.players.actions import RelativeCoordinate, SetOfMarksLocation
from gptnt.players.defuser import DefuserResultT, MDPDefuserPlayer
from gptnt.players.expert import ExpertPlayer, ExpertResultT


class PlayerCases:
    """Parametrize fixtures for players."""

    def case_expert(self, dialogue_space_client: DialogueSpaceClient) -> ExpertPlayer:
        expert_agent = Agent[None, ExpertResultT]("test", result_type=ExpertResultT)
        return ExpertPlayer(agent=expert_agent, dialogue_space_client=dialogue_space_client)

    def case_defuser_mdp_set_of_marks(
        self, dialogue_space_client: DialogueSpaceClient, game_client: KtaneClient
    ) -> MDPDefuserPlayer[SetOfMarksLocation]:
        agent = Agent[None, DefuserResultT[SetOfMarksLocation]](
            "test", result_type=DefuserResultT[SetOfMarksLocation]
        )
        return MDPDefuserPlayer[SetOfMarksLocation](
            agent=agent, dialogue_space_client=dialogue_space_client, game_client=game_client
        )

    def case_defuser_mdp_coordinate(
        self, dialogue_space_client: DialogueSpaceClient, game_client: KtaneClient
    ) -> MDPDefuserPlayer[RelativeCoordinate]:
        agent = Agent[None, DefuserResultT[RelativeCoordinate]](
            "test", result_type=DefuserResultT[RelativeCoordinate]
        )
        return MDPDefuserPlayer[RelativeCoordinate](
            agent=agent, dialogue_space_client=dialogue_space_client, game_client=game_client
        )
