import itertools
from typing import NamedTuple

import structlog

from gptnt.api.experiment_manager.structures import ConnectedPlayerService
from gptnt.experiments.experiments import ExperimentSpec

logger = structlog.get_logger()


class PlayerExperimentPairing(NamedTuple):
    """Pairing of an experiment and players."""

    experiment: ExperimentSpec
    defuser: ConnectedPlayerService
    expert: ConnectedPlayerService | None


def find_valid_pairing_for_single_player(
    *, available_players: list[ConnectedPlayerService], experiment: ExperimentSpec
) -> PlayerExperimentPairing | None:
    """Find a valid pairing of players for the given single player experiment.

    Returns None if no valid pairing is found.
    """
    for player in available_players:
        if player.player_metadata.player_name == experiment.defuser_name:
            return PlayerExperimentPairing(experiment=experiment, defuser=player, expert=None)
    return None


def find_valid_pairing_for_multi_player(
    *, available_players: list[ConnectedPlayerService], experiment: ExperimentSpec
) -> PlayerExperimentPairing | None:
    """Find a valid pairing of players for the given multi player experiment.

    Returns None if no valid pairing is found.
    """
    if experiment.is_single_player or experiment.expert_name is None:
        return None

    for player1, player2 in itertools.permutations(available_players, 2):
        if (
            player1.player_metadata.player_name == experiment.defuser_name
            and player2.player_metadata.player_name == experiment.expert_name
        ):
            return PlayerExperimentPairing(experiment=experiment, defuser=player1, expert=player2)
    return None


def get_playable_pairings(
    *, available_players: list[ConnectedPlayerService], available_experiments: list[ExperimentSpec]
) -> list[PlayerExperimentPairing]:
    """Return all currently playable pairings of players and experiments."""
    pairings: list[PlayerExperimentPairing] = []

    if not available_experiments or not available_players:
        # No experiments or players available
        return pairings

    single_player_experiments = [exp for exp in available_experiments if exp.is_single_player]
    for experiment in single_player_experiments:
        pairing = find_valid_pairing_for_single_player(
            available_players=available_players, experiment=experiment
        )
        if pairing is not None:
            pairings.append(pairing)
            available_players.remove(pairing.defuser)

    multi_player_experiments = [exp for exp in available_experiments if not exp.is_single_player]
    for experiment in multi_player_experiments:
        pairing = find_valid_pairing_for_multi_player(
            available_players=available_players, experiment=experiment
        )
        if pairing is not None:
            pairings.append(pairing)
            available_players.remove(pairing.defuser)
            assert pairing.expert is not None
            available_players.remove(pairing.expert)
    return pairings
