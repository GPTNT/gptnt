"""Assemble the real interactive services in one process against a fake-Redis DSN.

Mirrors the production entrypoints (`run_experiment_manager` builds the EM, `run_game_instance` /
`run_player` build the services) but colocates them and connects their *real* brokers to the in-
process fake server, so cross-service RPC + matchmaking + the experiment runner all execute for
real. The game binary is replaced by `FakeKtaneGame` (installed by the caller before assembly).
"""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import anyio
from coredis import Redis

from gptnt.experiments.spec import Condition, ExperimentSpec
from gptnt.interactive.entrypoints.run_game_instance import main as build_game_app
from gptnt.interactive.entrypoints.run_player import main as build_player_app
from gptnt.interactive.services.broker import create_redis_broker
from gptnt.interactive.services.experiment_manager.experiment_manager import ExperimentManager
from gptnt.interactive.services.experiment_manager.experiment_runner import ExperimentState
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.modules import KtaneComponent
from gptnt.specification import CommunicationStyle, PlayerProtocol

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from gptnt.interactive.services.experiment_manager.session import Session
    from gptnt.interactive.services.game.service import GameService
    from gptnt.interactive.services.player.service import PlayerService

_POLL = 0.1
_STARTUP_TIMEOUT = 15.0


@dataclass
class AssembledExperiment:
    """The live, colocated services for one experiment run."""

    experiment_manager: ExperimentManager
    game: GameService
    defuser: PlayerService
    expert: PlayerService | None

    async def wait_until_ready(self, timeout: float = 15.0) -> None:  # noqa: ASYNC109
        """Block until the game and all players have registered as ready with the manager."""
        expected_players = 1 if self.expert is None else 2
        with anyio.fail_after(timeout):
            while True:
                games_ready = any(
                    game.uuid == self.game.uuid for game in self.experiment_manager.ready_games
                )
                if games_ready and len(self.experiment_manager.ready_players) >= expected_players:
                    return
                await anyio.sleep(_POLL)

    def build_spec(
        self,
        *,
        seed: int = 234,
        component: KtaneComponent = KtaneComponent.big_button,
        time_limit: int = 300,
        num_strikes_allowed: int = 3,
        communication_style: CommunicationStyle = "sync",
        condition: Condition = "single_module",
    ) -> ExperimentSpec:
        """Build a spec whose player names match the assembled services (so matchmaking pairs)."""
        is_solo = self.expert is None
        expert_protocol = (
            None
            if is_solo
            else PlayerProtocol(
                role="expert",
                communication_style=communication_style,
                is_playing_alone=False,
                include_manual=True,
            )
        )
        return ExperimentSpec(
            mission_spec=KtaneMissionSpec(
                seed=seed,
                time_limit=time_limit,
                num_strikes_allowed=num_strikes_allowed,
                components=[component],
                optional_widgets=1,
            ),
            condition=condition,
            defuser_protocol=PlayerProtocol(
                role="defuser",
                communication_style=communication_style,
                is_playing_alone=is_solo,
                include_manual=True,
            ),
            defuser_name=self.defuser.capabilities.player_name,
            expert_protocol=expert_protocol,
            expert_name=self.expert.capabilities.player_name if self.expert else None,
        )

    async def run_to_completion(
        self, spec: ExperimentSpec, *, fail_after: float = 60.0
    ) -> Session:
        """Submit `spec` and wait for the matched session to reach `ExperimentState.done`."""
        self.experiment_manager.specs.add(spec)
        session: Session | None = None
        with anyio.fail_after(fail_after):
            while True:
                if session is None and self.experiment_manager.active_sessions:
                    session = next(iter(self.experiment_manager.active_sessions))
                if session is not None and session.state == ExperimentState.done:
                    return session
                await anyio.sleep(_POLL)


@asynccontextmanager
async def assembled_experiment(
    dsn: str, *, defuser_model: str = "test_defuser", expert_model: str | None = "test_expert"
) -> AsyncIterator[AssembledExperiment]:
    """Build EM + game + player services against `dsn` and run all their lifespans."""
    experiment_manager = ExperimentManager(
        redis=Redis.from_url(dsn, decode_responses=True),
        redis_broker=create_redis_broker(dsn, client_name="experiment_manager"),
    )

    game_app = build_game_app(redis_dsn=dsn)
    game_service = game_app.context.get("game_service")
    assert game_service is not None, (
        "FastStream context injection returned None for 'game_service'. "
        "The app must inject context at construction time — check run_game_instance.main()."
    )

    defuser_app = build_player_app(redis_dsn=dsn, hydra_overrides=[f"model={defuser_model}"])
    defuser_service = defuser_app.context.get("player_service")
    assert defuser_service is not None, (
        "FastStream context injection returned None for 'player_service' (defuser). "
        "Check run_player.main()."
    )

    expert_service = None
    if expert_model is not None:
        expert_app = build_player_app(redis_dsn=dsn, hydra_overrides=[f"model={expert_model}"])
        expert_service = expert_app.context.get("player_service")
        assert expert_service is not None, (
            "FastStream context injection returned None for 'player_service' (expert). "
            "Check run_player.main()."
        )

    services = [game_service, defuser_service, *([expert_service] if expert_service else [])]
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(experiment_manager.lifespan())
        for service in services:
            await stack.enter_async_context(service.lifespan())  # noqa: WPS476

        # Each `lifespan` enters `async with self.broker`, which only *connects* the broker —
        # it does NOT start the registered subscribers (in production `FastStream.run()` calls
        # `broker.start()` for us). Without this, the RPC command subscribers (configure_player,
        # configure_game, ...) never consume, so the runner's first `broker.request` blocks until
        # `redis_rpc_timeout` (600s) and the run looks like an infinite hang. Start them here.
        for broker in (experiment_manager.redis_broker, *(svc.broker for svc in services)):
            _ = await broker.start()

        experiment = AssembledExperiment(
            experiment_manager=experiment_manager,
            game=game_service,
            defuser=defuser_service,
            expert=expert_service,
        )

        # Surface startup failures instead of letting them be masked. Each lifespan starts
        # background tasks (heartbeat loops, the game state monitor) via `start_soon` inside a task
        # group that this AsyncExitStack holds open. If one of those tasks raises during startup,
        # anyio's task-group teardown absorbs it and `@asynccontextmanager` reports the cryptic
        # `RuntimeError: generator didn't yield` with no clue as to why. Actively waiting for
        # readiness here turns a failed/stuck startup into an actionable error at assembly time;
        # the real exception is logged by the offending service (see broadcaster / state_monitor).
        try:
            await experiment.wait_until_ready(timeout=_STARTUP_TIMEOUT)
        except TimeoutError as exc:
            raise RuntimeError(
                f"assembled_experiment: game/players never became ready within {_STARTUP_TIMEOUT}s. A startup task likely failed — re-run the test with `-s` (or read the captured  service logs above) for the underlying exception."
            ) from exc

        yield experiment
