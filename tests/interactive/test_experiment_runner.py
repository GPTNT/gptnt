"""Tests for experiment-wide state selected by the experiment runner."""

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock

import anyio
import pytest

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
async def test_player_configuration_shares_one_experiment_provenance_snapshot() -> None:
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
    defuser_configure = AsyncMock(return_value=True)
    expert_configure = AsyncMock(return_value=True)
    runner.defuser_player_client = cast(
        "PlayerClient", cast("object", SimpleNamespace(configure_player=defuser_configure))
    )
    runner.expert_player_client = cast(
        "PlayerClient", cast("object", SimpleNamespace(configure_player=expert_configure))
    )
    runner.game_client = cast(
        "GameClient",
        cast(
            "object",
            SimpleNamespace(
                configure_game=AsyncMock(return_value=None),
                pause_game=AsyncMock(return_value=None),
            ),
        ),
    )
    runner.game_state_watcher = cast(
        "GameStateWatcher", cast("object", SimpleNamespace(lights_are_off_event=lights_are_off))
    )

    await runner.configure_services()

    assert defuser_configure.await_args is not None
    assert expert_configure.await_args is not None
    defuser_provenance = defuser_configure.await_args.kwargs["provenance"]
    expert_provenance = expert_configure.await_args.kwargs["provenance"]
    assert defuser_provenance is runner.provenance
    assert expert_provenance is runner.provenance
