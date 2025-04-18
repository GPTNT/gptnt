from pydantic_ai import Agent

from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.ktane.actions import RelativeCoordinate
from gptnt.ktane.client import KtaneClient
from gptnt.players.actions import SetOfMarksLocation
from gptnt.players.ai.defuser import DefuserOutputT, MDPDefuserPlayer
from gptnt.players.ai.expert import ExpertOutputT, ExpertPlayer


class AIPlayerCases:
    """Parametrize fixtures for players."""

    def case_expert(self, dialogue_space_client: DialogueSpaceClient) -> ExpertPlayer:
        expert_agent = Agent[None, ExpertOutputT]("test", output_type=ExpertOutputT)
        return ExpertPlayer(agent=expert_agent, dialogue_space_client=dialogue_space_client)

    def case_defuser_mdp_set_of_marks(
        self, dialogue_space_client: DialogueSpaceClient, game_client: KtaneClient
    ) -> MDPDefuserPlayer[SetOfMarksLocation]:
        agent = Agent[None, DefuserOutputT[SetOfMarksLocation]](
            "test", output_type=DefuserOutputT[SetOfMarksLocation]
        )
        return MDPDefuserPlayer[SetOfMarksLocation](
            agent=agent, dialogue_space_client=dialogue_space_client, game_client=game_client
        )

    def case_defuser_mdp_coordinate(
        self, dialogue_space_client: DialogueSpaceClient, game_client: KtaneClient
    ) -> MDPDefuserPlayer[RelativeCoordinate]:
        agent = Agent[None, DefuserOutputT[RelativeCoordinate]](
            "test", output_type=DefuserOutputT[RelativeCoordinate]
        )
        return MDPDefuserPlayer[RelativeCoordinate](
            agent=agent, dialogue_space_client=dialogue_space_client, game_client=game_client
        )
