"""Tests for experiment-wide state selected by the experiment runner."""

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import anyio
import pytest
from pytest_mock import MockerFixture

from gptnt.interactive.services.experiment_manager.experiment_runner import SyncExperimentRunner
from gptnt.players.specification import PlayerProtocol

from tests._factories.experiments import (
    make_experiment_instance,
    make_experiment_spec,
    make_provenance,
)

if TYPE_CHECKING:
    from gptnt.interactive.services.game.client import GameClient
    from gptnt.interactive.services.heartbeat.watcher import GameStateWatcher
    from gptnt.interactive.services.player.client import PlayerClient


@pytest.mark.anyio
async def test_player_configuration_shares_one_experiment_provenance_snapshot(
    mocker: MockerFixture,
) -> None:
    """Defuser and expert configuration receive the runner's one captured snapshot."""
    defuser_protocol = PlayerProtocol(
        role="defuser", communication_style="sync", is_playing_alone=False, include_manual=False
    )
    expert_protocol = PlayerProtocol(
        role="expert", communication_style="sync", is_playing_alone=False, include_manual=True
    )
    experiment = make_experiment_instance(
        make_experiment_spec().model_copy(
            update={
                "defuser_protocol": defuser_protocol,
                "expert_protocol": expert_protocol,
                "expert_name": "test-expert",
            }
        )
    )

    # Isolate service orchestration while retaining the production configure_services method.
    lights_are_off = anyio.Event()
    lights_are_off.set()
    runner = object.__new__(SyncExperimentRunner)
    runner.experiment = experiment
    runner.provenance = make_provenance()
    defuser_configure = mocker.AsyncMock(return_value=True)
    expert_configure = mocker.AsyncMock(return_value=True)
    runner.defuser_player_client = cast(
        "PlayerClient", cast("object", SimpleNamespace(configure_player=defuser_configure))
    )
    runner.expert_player_client = cast(
        "PlayerClient", cast("object", SimpleNamespace(configure_player=expert_configure))
    )
    configure_game = mocker.AsyncMock(return_value=None)
    pause_game = mocker.AsyncMock(return_value=None)
    runner.game_client = cast(
        "GameClient",
        cast("object", SimpleNamespace(configure_game=configure_game, pause_game=pause_game)),
    )
    runner.game_state_watcher = cast(
        "GameStateWatcher", cast("object", SimpleNamespace(lights_are_off_event=lights_are_off))
    )

    await runner.configure_services()

    defuser_configure.assert_awaited_once_with(
        player_protocol=defuser_protocol,
        experiment_instance=experiment,
        provenance=runner.provenance,
    )
    expert_configure.assert_awaited_once_with(
        player_protocol=expert_protocol,
        experiment_instance=experiment,
        provenance=runner.provenance,
    )
    configure_game.assert_awaited_once_with(
        spec=experiment.mission_spec, session_id=experiment.session_id
    )
    pause_game.assert_awaited_once_with()
