from contextlib import suppress
from typing import NamedTuple

import structlog

from gptnt.api.player_client import SupervisedPlayerClient
from gptnt.ktane.experiments.experiments import ExperimentSpec

logger = structlog.get_logger()


# BUG: Can't move to structures.py because of circular imports
class PlayerExperimentPairing(NamedTuple):
    """Pairing of an experiment and players."""

    expert: SupervisedPlayerClient
    defuser: SupervisedPlayerClient
    experiment: ExperimentSpec


def get_required_experiments() -> set[ExperimentSpec]:
    """Returns the set of missions each human is required to play before entering free-play."""
    return set()


def _get_demo_pairings(  # noqa: WPS231
    available_players: set[SupervisedPlayerClient],
) -> list[PlayerExperimentPairing]:
    """Returns all valid pairings for demo/required experiments."""
    pairings: list[PlayerExperimentPairing] = []

    # Seperate human and AI players
    human_players: set[SupervisedPlayerClient] = {
        player for player in available_players if player.metadata.player_type == "human"
    }
    ai_defusers: set[SupervisedPlayerClient] = {
        player
        for player in available_players
        if player.metadata.player_type == "ai" and player.metadata.player_role == "defuser"
    }
    ai_experts: set[SupervisedPlayerClient] = {
        player
        for player in available_players
        if player.metadata.player_type == "ai" and player.metadata.player_role == "expert"
    }

    # All human players should finish the required experiments before entering free-play
    # Human players should prioritise being paired with other humans for required experiments
    # Any leftover human will be paired with a random AI as the defuser
    # BUG: For the required missions, since they are meant to teach the system, it would be good for humans to be both roles
    for required_experiment in get_required_experiments():
        required_players = [
            player
            for player in human_players
            if required_experiment not in player.metadata.experiments_played
        ]

        while len(required_players) >= 2:  # noqa: PLR2004
            pairings.append(
                PlayerExperimentPairing(
                    expert=required_players.pop(),
                    defuser=required_players.pop(),
                    experiment=required_experiment,
                )
            )

        if len(required_players) != 0 and len(ai_defusers) != 0:
            pairings.append(
                PlayerExperimentPairing(
                    expert=required_players.pop(),
                    defuser=ai_defusers.pop(),
                    experiment=required_experiment,
                )
            )

        if len(required_players) != 0 and len(ai_experts) != 0:
            pairings.append(
                PlayerExperimentPairing(
                    expert=required_players.pop(),
                    defuser=ai_experts.pop(),
                    experiment=required_experiment,
                )
            )

    return pairings


def _get_freeplay_pairings(  # noqa: WPS231
    available_players: set[SupervisedPlayerClient], available_experiments: set[ExperimentSpec]
) -> list[PlayerExperimentPairing]:
    """Returns all valid pairings for freeplay experiments."""
    pairings: list[PlayerExperimentPairing] = []

    # Free play, all players are now valid
    if len(available_experiments) == 0:
        return pairings

    # Experiments will be completed in an unspecified order
    for experiment in available_experiments:
        valid_experts = {
            player
            for player in available_players
            if player.metadata.player_name is experiment.pairing.expert
            and (player.metadata.player_type == "human" or player.metadata.player_role == "expert")
            and experiment not in player.metadata.experiments_played
        }
        valid_defusers = {
            player
            for player in available_players
            if player.metadata.player_name is experiment.pairing.defuser
            and (
                player.metadata.player_type == "human" or player.metadata.player_role == "defuser"
            )
            and experiment not in player.metadata.experiments_played
        }

        if len(valid_experts) == 0:
            continue
        expert = valid_experts.pop()

        with suppress(KeyError):
            valid_defusers.remove(expert)

        if len(valid_defusers) == 0:
            continue
        defuser = valid_defusers.pop()

        available_players.remove(expert)
        available_players.remove(defuser)
        pairings.append(
            PlayerExperimentPairing(expert=expert, defuser=defuser, experiment=experiment)
        )

    return pairings


def get_playable_pairings(
    available_players: set[SupervisedPlayerClient], available_experiments: set[ExperimentSpec]
) -> list[PlayerExperimentPairing]:
    """Returns all currently playable experiment pairings, proritizing demo experiments."""
    demo_pairings = _get_demo_pairings(available_players=available_players)
    freeplay_pairings = _get_freeplay_pairings(
        available_players=available_players, available_experiments=available_experiments
    )
    return demo_pairings + freeplay_pairings
