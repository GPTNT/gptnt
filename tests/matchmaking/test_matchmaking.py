from gptnt.api.player_client import PlayerClient, SupervisedPlayerClient
from gptnt.api.tinder import get_playable_pairings
from gptnt.ktane.experiments.experiments import ExperimentSpec
from gptnt.ktane.experiments.pairing import Pairing
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.players.structures import PlayerMetadata


def create_player(player_name: str, player_role: str = "") -> SupervisedPlayerClient:
    return SupervisedPlayerClient(
        client=PlayerClient(url=""),
        metadata=PlayerMetadata(
            fastapi_url="",
            player_type="human" if player_name == "human" else "ai",
            player_role=player_role,
            player_name=player_name,
        ),
    )


def create_experiment(expert: str, defuser: str) -> ExperimentSpec:
    return ExperimentSpec(
        mission_spec=KtaneMissionSpec(seed=0, time_limit=1, optional_widgets=0, components=[]),
        condition="single_module",
        pairing=Pairing(expert=expert, defuser=defuser),
        communication_style="parallel",
    )


def get_players() -> set[SupervisedPlayerClient]:
    return {
        create_player(player_name="claude-37", player_role="expert"),
        create_player(player_name="claude-37", player_role="defuser"),
        create_player(player_name="gemini", player_role="expert"),
        create_player(player_name="gemini", player_role="defuser"),
    }


def test_aiai_4p0e() -> None:
    """Tests if pairings are generated if no experiments are queued."""
    available_players = get_players()
    available_experiments = set()
    pairings = get_playable_pairings(
        available_players=available_players, available_experiments=available_experiments
    )
    assert len(pairings) == 0


def test_aiai_4p1e() -> None:
    """Tests if only one paring is generated if only one experiment is queued."""
    available_players = get_players()
    available_experiments = {create_experiment(expert="claude-37", defuser="claude-37")}
    pairings = get_playable_pairings(
        available_players=available_players, available_experiments=available_experiments
    )
    assert len(pairings) == 1


def test_aiai_4p2e_nomacth() -> None:
    """Tests if only one paring is generated if two experiments are queued, but only one can be
    played."""
    available_players = get_players()
    available_experiments = {
        create_experiment(expert="claude-37", defuser="claude-37"),
        create_experiment(expert="gemini", defuser="claude-37"),
    }
    pairings = get_playable_pairings(
        available_players=available_players, available_experiments=available_experiments
    )
    assert len(pairings) == 1


def test_aiai_2_experiments() -> None:
    """Tests if multiple pairings can be generated if there are enough players and queued
    experiments."""
    available_players = get_players()
    available_experiments = {
        create_experiment(expert="claude-37", defuser="claude-37"),
        create_experiment(expert="gemini", defuser="gemini"),
    }
    pairings = get_playable_pairings(
        available_players=available_players, available_experiments=available_experiments
    )
    assert len(pairings) == 2
