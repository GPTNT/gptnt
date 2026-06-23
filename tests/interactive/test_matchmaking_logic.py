"""Unit tests for matchmaking pairing logic (pure functions, no Redis)."""

from __future__ import annotations

from uuid import uuid4

from gptnt.core.ktane.mission_spec import KtaneMissionSpec
from gptnt.core.ktane.state.modules import KtaneComponent
from gptnt.core.specification import PlayerProtocol
from gptnt.experiments.spec import ExperimentSpec
from gptnt.interactive.services.experiment_manager.matchmaking import get_playable_pairings
from gptnt.interactive.services.heartbeat.base import PlayerState, ReadyState
from gptnt.interactive.services.heartbeat.player import PlayerHeartbeat
from gptnt.interactive.services.registry.manifest import PlayerServiceManifest, ServiceManifest

from tests._factories.players import PlayerCapabilitiesFactory


def make_player(
    player_name: str, *, state: PlayerState = PlayerState.idle
) -> PlayerServiceManifest:
    """Build a player manifest with the given matchmaking name."""
    heartbeat = PlayerHeartbeat(
        uuid=uuid4(),
        service_name=player_name,
        ready_state=ReadyState.ready,
        capabilities=PlayerCapabilitiesFactory.build(player_name=player_name),
        state=state,
    )
    return ServiceManifest(heartbeat=heartbeat)


def make_spec(*, defuser_name: str, expert_name: str | None = None) -> ExperimentSpec:
    """Build a single- or multi-player spec keyed on the given player names."""
    is_solo = expert_name is None
    return ExperimentSpec(
        mission_spec=KtaneMissionSpec(
            seed=1,
            time_limit=300,
            num_strikes_allowed=3,
            components=[KtaneComponent.big_button],
            optional_widgets=1,
        ),
        condition="single_module",
        defuser_protocol=PlayerProtocol(
            role="defuser",
            communication_style="sync",
            is_playing_alone=is_solo,
            include_manual=True,
        ),
        defuser_name=defuser_name,
        expert_protocol=(
            None
            if is_solo
            else PlayerProtocol(
                role="expert",
                communication_style="sync",
                is_playing_alone=False,
                include_manual=True,
            )
        ),
        expert_name=expert_name,
    )


def test_single_player_pairs_by_name() -> None:
    player = make_player("test-defuser")
    spec = make_spec(defuser_name="test-defuser")

    pairings = get_playable_pairings(available_players=[player], available_experiments=[spec])

    assert len(pairings) == 1
    assert pairings[0].defuser is player
    assert pairings[0].expert is None
    assert pairings[0].experiment is spec


def test_no_pairing_when_defuser_name_mismatches() -> None:
    player = make_player("someone-else")
    spec = make_spec(defuser_name="test-defuser")

    assert get_playable_pairings(available_players=[player], available_experiments=[spec]) == []


def test_multi_player_pairs_defuser_and_expert() -> None:
    defuser = make_player("the-defuser")
    expert = make_player("the-expert")
    spec = make_spec(defuser_name="the-defuser", expert_name="the-expert")

    pairings = get_playable_pairings(
        available_players=[defuser, expert], available_experiments=[spec]
    )

    assert len(pairings) == 1
    assert pairings[0].defuser is defuser
    assert pairings[0].expert is expert


def test_multi_player_needs_both_players_present() -> None:
    defuser = make_player("the-defuser")
    spec = make_spec(defuser_name="the-defuser", expert_name="the-expert")

    assert get_playable_pairings(available_players=[defuser], available_experiments=[spec]) == []


def test_no_pairings_without_players_or_experiments() -> None:
    player = make_player("the-defuser")
    spec = make_spec(defuser_name="the-defuser")

    assert get_playable_pairings(available_players=[], available_experiments=[spec]) == []
    assert get_playable_pairings(available_players=[player], available_experiments=[]) == []
