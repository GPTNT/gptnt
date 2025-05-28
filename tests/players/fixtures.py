# from pydantic_ai import Agent

# from gptnt.dialogue_space.client import DialogueSpaceClient
# from gptnt.ktane.actions import RelativeCoordinate
# from gptnt.ktane.client import KtaneClient
# from gptnt.players.actions import SetOfMarksLocation
# # from gptnt.players.ai.defuser import DefuserOutputT, MDPDefuserPlayer
# # from gptnt.players.ai.expert import ExpertOutputT, ExpertPlayer
# from gptnt.players.metrics.tracker import PlayerEpisodeTracker
# from gptnt.players.structures import PlayerMetadata


# class AIPlayerCases:
#     """Parametrize fixtures for players."""

#     def case_expert(
#         self,
#         dialogue_space_client: DialogueSpaceClient,
#         player_episode_tracker: PlayerEpisodeTracker,
#     ) -> ExpertPlayer:
#         expert_agent = Agent[None, ExpertOutputT]("test", output_type=ExpertOutputT)
#         player = ExpertPlayer(
#             agent=expert_agent,
#             metadata=PlayerMetadata(player_type="ai", player_role="expert"),
#             tracker=player_episode_tracker,
#         )
#         player.dialogue_space_client = dialogue_space_client
#         return player

#     def case_defuser_mdp_set_of_marks(
#         self,
#         dialogue_space_client: DialogueSpaceClient,
#         game_client: KtaneClient,
#         player_episode_tracker: PlayerEpisodeTracker,
#     ) -> MDPDefuserPlayer[SetOfMarksLocation]:
#         agent = Agent[None, DefuserOutputT[SetOfMarksLocation]](
#             "test", output_type=DefuserOutputT[SetOfMarksLocation]
#         )
#         player = MDPDefuserPlayer[SetOfMarksLocation](
#             agent=agent,
#             game_client=game_client,
#             metadata=PlayerMetadata(player_type="ai", player_role="defuser"),
#             tracker=player_episode_tracker,
#         )
#         player.dialogue_space_client = dialogue_space_client
#         return player

#     def case_defuser_mdp_coordinate(
#         self,
#         dialogue_space_client: DialogueSpaceClient,
#         game_client: KtaneClient,
#         player_episode_tracker: PlayerEpisodeTracker,
#     ) -> MDPDefuserPlayer[RelativeCoordinate]:
#         agent = Agent[None, DefuserOutputT[RelativeCoordinate]](
#             "test", output_type=DefuserOutputT[RelativeCoordinate]
#         )
#         player = MDPDefuserPlayer[RelativeCoordinate](
#             agent=agent,
#             game_client=game_client,
#             metadata=PlayerMetadata(player_type="ai", player_role="defuser"),
#             tracker=player_episode_tracker,
#         )
#         player.dialogue_space_client = dialogue_space_client
#         return player
