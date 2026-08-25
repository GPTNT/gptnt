"""Tests for experiment-wide state selected by the experiment runner."""

from contextlib import nullcontext
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock, Mock

import anyio
import pytest
from pytest_mock import MockerFixture

from gptnt.interactive.services.experiment_manager.experiment_runner import (
    AsyncExperimentRunner,
    SyncExperimentRunner,
)
from gptnt.interactive.services.game.client import GameClient
from gptnt.interactive.services.heartbeat.watcher import GameStateWatcher, PlayerStateWatcher
from gptnt.interactive.services.player.client import PlayerClient
from gptnt.players.specification import PlayerProtocol

from tests._factories.experiments import (
    make_experiment_instance,
    make_experiment_spec,
    make_provenance,
)

if TYPE_CHECKING:
    from coredis import Redis
    from faststream.redis import RedisBroker


@dataclass(kw_only=True)
class _BlockedPlayer:
    """Block the player request until the runner cancels its task."""

    started: anyio.Event
    cancelled: anyio.Event

    async def forward_pass(self) -> None:
        """Wait until cancellation and record that it occurred."""
        self.started.set()
        try:
            await anyio.sleep_forever()
        except BaseException:
            self.cancelled.set()
            raise


async def _run_until_completion(runner: AsyncExperimentRunner, completed: anyio.Event) -> None:
    """Run the async loop and record its normal return."""
    await runner.run_experiment_loop()
    completed.set()


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


@pytest.mark.anyio
async def test_async_runner_cancels_an_inflight_player_rpc_when_the_game_ends(
    mocker: MockerFixture,
) -> None:
    """A completed game must not wait for a player RPC's normal timeout before cleanup begins."""
    game_over = anyio.Event()
    player_started = anyio.Event()
    player_cancelled = anyio.Event()
    runner_completed = anyio.Event()
    blocked_player = _BlockedPlayer(started=player_started, cancelled=player_cancelled)
    _ = mocker.patch(
        "gptnt.interactive.services.experiment_manager.experiment_runner.Provenance.capture",
        return_value=make_provenance(),
    )
    game_watcher = mocker.MagicMock(
        spec=GameStateWatcher,
        game_over_event=game_over,
        is_game_over=False,
        is_hard_crash=False,
        temporary_update_interval=Mock(return_value=nullcontext()),
    )
    game_client = mocker.Mock(spec=GameClient, unpause_game=mocker.AsyncMock())
    defuser_player_client = mocker.Mock(
        spec=PlayerClient, forward_pass=blocked_player.forward_pass
    )
    defuser_state_watcher = mocker.Mock(spec=PlayerStateWatcher, is_hard_crash=False)

    runner = AsyncExperimentRunner(
        experiment=make_experiment_instance(),
        redis=cast("Redis[str]", MagicMock()),
        redis_broker=cast("RedisBroker", MagicMock()),
    )
    runner.game_client = game_client
    runner.defuser_player_client = defuser_player_client
    runner.expert_player_client = None
    runner.game_state_watcher = game_watcher
    runner.defuser_state_watcher = defuser_state_watcher
    runner.expert_state_watcher = None

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(_run_until_completion, runner, runner_completed)
        await player_started.wait()
        game_over.set()
        with anyio.fail_after(1):
            await player_cancelled.wait()
            await runner_completed.wait()

    assert player_cancelled.is_set()
    assert runner_completed.is_set()
