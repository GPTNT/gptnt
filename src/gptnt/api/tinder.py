from contextlib import suppress
from typing import NamedTuple

import structlog

from gptnt.api.player_client import SupervisedPlayerClient
from gptnt.experiments.experiments import ExperimentSpec

logger = structlog.get_logger()


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

    # Separate human and AI players
    human_players: set[SupervisedPlayerClient] = {
        player for player in available_players if player.metadata.player_type == "human"
    }
    if len(human_players) == 0:
        return pairings

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


def find_valid_pairing_for_experiment(
    *, available_players: set[SupervisedPlayerClient], experiment: ExperimentSpec
) -> PlayerExperimentPairing | None:
    """Returns a valid pairing for the given experiment."""
    valid_experts = {
        player
        for player in available_players
        # Check the player is the desired expert for this experiment
        if player.metadata.player_name == experiment.pairing.expert
        # And that the experiment has not been played by this player yet
        and experiment not in player.metadata.experiments_played
        # And also check that the player is a human OR is an AI with the correct role
        # TODO: this might be a source of a bug?? Depends on how we run them
        and (player.metadata.player_type == "human" or player.metadata.player_role == "expert")
    }

    valid_defusers = {
        player
        for player in available_players
        # Check the player is the desired defuser for this experiment
        if player.metadata.player_name == experiment.pairing.defuser
        # And also check that the player has not played this experiment yet
        and experiment not in player.metadata.experiments_played
        # And also check that the player is a human OR is an AI with the correct role
        # TODO: this might be a source of a bug?? Depends on how we run them
        and (player.metadata.player_type == "human" or player.metadata.player_role == "defuser")
    }

    # If there are no valid experts, skip
    if len(valid_experts) == 0:
        return None

    expert = valid_experts.pop()

    # If there are no valid defusers, skip
    with suppress(KeyError):
        valid_defusers.remove(expert)
    if len(valid_defusers) == 0:
        return None

    defuser = valid_defusers.pop()
    return PlayerExperimentPairing(expert=expert, defuser=defuser, experiment=experiment)


def _get_freeplay_pairings(  # noqa: WPS231
    available_players: set[SupervisedPlayerClient], available_experiments: set[ExperimentSpec]
) -> list[PlayerExperimentPairing]:
    """Returns all valid pairings for freeplay experiments."""
    pairings: list[PlayerExperimentPairing] = []

    # Free play, all players are now valid
    if not available_experiments:
        return pairings

    # Experiments will be completed in an unspecified order
    for experiment in available_experiments:
        pairing = find_valid_pairing_for_experiment(
            available_players=available_players, experiment=experiment
        )
        if pairing is not None:
            pairings.append(pairing)
            available_players.remove(pairing.expert)
            available_players.remove(pairing.defuser)

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
