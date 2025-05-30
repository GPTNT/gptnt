import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass, field
from functools import cached_property
from types import TracebackType
from typing import Any, override

import logfire
from pydantic.types import UUID4
from structlog import get_logger

from gptnt.api.base_em_client import BaseEMClient
from gptnt.api.base_rabbitmq_client import ExceptionUnhandledError
from gptnt.api.commands import (
    AdvanceTimeGameCommand,
    GameDoneCommand,
    GameGetObservationCommand,
    ReflectionCommand,
    RoomCommand,
    RunForwardOnceCommand,
    StartExperimentCommand,
    StopExperimentCommand,
    UnpauseGameCommand,
)
from gptnt.api.events import ExperimentDoneEvent, RoomConnectEvent
from gptnt.api.experiment_manager.experiment_bindings import (
    configure_experiment_services,
    remove_experiment_bindings,
    set_experiment_bindings,
)
from gptnt.api.experiment_manager.experiment_descriptor import ExperimentDescriptor
from gptnt.api.game_manager.game_instance import GameObservationResponse
from gptnt.common.async_ops import busy_wait_interval
from gptnt.experiments.time_limits import SECONDS_PER_ACTION
from gptnt.players.prompts import convert_bomb_state_to_reflection

logger = get_logger()

PLAYER_TIMEOUT_SECONDS = 600
"""Time to wait for a player to take an action before timing out."""
WAIT_FOR_GAME_DONE_SECONDS = 6000
"""Time to wait for a game to be done before timing out."""


class ConfigurationFailedError(Exception):
    """Error representing the failure to configure the room subservices."""


class PlayerTookTooLongError(Exception):
    """Error representing a player taking too long to take an action."""


class GameTooLongError(Exception):
    """Error representing a game taking too long.

    May wish to remove this error in the future.
    """


@dataclass(kw_only=True)
class RoomInstance(BaseEMClient):
    """Manages a room.

    Controls the lifecycle of an experiment.
    """

    _running_experiment: ExperimentDescriptor | None = field(default=None, init=False)
    _running_experiment_tasks: list[Coroutine[Any, Any, None]] = field(
        default_factory=list, init=False
    )

    _is_in_progress: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Synchronous startup logic to run BEFORE app start."""
        super().__post_init__()
        logger.info(f"Started RoomInstance with UUID: {self.uuid}")

        # TODO: Subscribe to queues
        self.api_queues.room_command(room_uuid=self.uuid).subscribe(self.handle_command)

    @cached_property
    @override
    def connection_message(self) -> RoomConnectEvent:
        """Specifies the connection message to send to the EM on startup."""
        return RoomConnectEvent(uuid=self.uuid)

    @override
    async def lifespan_setup(self) -> None:
        """Asynchronous logic to run after app startup."""
        await super().lifespan_setup()
        _ = self.background_tasks.create_task(self.ready())

    @override
    async def lifespan_cleanup(self) -> None:
        """Asynchronous logic to run during app shutdown."""

    @override
    async def handle_background_task_exception(
        self,
        exc_type: type[BaseException] | None = None,
        exc_obj: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        """Handle uncaught exceptions from background_tasks."""
        if isinstance(
            exc_obj, (ConfigurationFailedError, GameTooLongError, PlayerTookTooLongError)
        ):
            logger.warning(f"Stopping experiment due to error: {exc_obj}")
            await self.stop_experiment(hard_crash=True)
        else:
            raise ExceptionUnhandledError

    async def handle_command(self, command: RoomCommand) -> None:
        """Handle commands received from the EM."""
        logger.info(f"Recieved command: {command}")

        if isinstance(command, StartExperimentCommand):
            self._running_experiment_tasks.append(
                experiment_task := self.run_experiment(command.experiment_descriptor)
            )
            _ = self.background_tasks.create_task(experiment_task)

        if isinstance(command, StopExperimentCommand):
            await self.stop_experiment(hard_crash=command.hard_crash)

    async def run_experiment(self, experiment: ExperimentDescriptor) -> None:
        """Runs an experiment lifecycle."""
        if self._running_experiment:
            logger.warning("Tried to start experiment whilst one is already running.")
            return

        self._running_experiment = experiment

        # 1. Set up the queue bindings
        await set_experiment_bindings(
            experiment=experiment, api_queues=self.api_queues, api_routes=self.api_routes
        )

        # 2. Wait for the services to enter the correct configuration
        if not await configure_experiment_services(
            experiment=experiment, api_queues=self.api_queues, fail_after=30.0
        ):
            # TODO: Handle this error
            raise ConfigurationFailedError

        # 3. Run the agent forward loop
        self._is_in_progress = True
        logger.info("Starting experiment")
        await self.api_queues.game_command(experiment.game_uuid).route.publish(
            UnpauseGameCommand()
        )
        self._running_experiment_tasks.append(
            experiment_loop_task := self.async_experiment_loop(experiment)
            if experiment.experiment_spec.defuser_player_spec.communication_style == "async"
            else self.sync_experiment_loop(experiment)
        )
        experiment_loop = self.background_tasks.create_task(experiment_loop_task)

        is_game_done = await self.api_queues.game_done(
            experiment.game_uuid
        ).route.publish_with_ack(GameDoneCommand(), fail_after=WAIT_FOR_GAME_DONE_SECONDS)
        logger.debug(f"Game done: {is_game_done}")
        if not is_game_done:
            raise GameTooLongError

        # Stop the experiment loop
        self._is_in_progress = False
        is_loop_done = experiment_loop.done()
        logger.debug(f"Experiment loop over: {is_loop_done}")

        # 4. We are done
        _ = self.background_tasks.create_task(self.stop_experiment(hard_crash=False))

    async def sync_experiment_loop(self, experiment: ExperimentDescriptor) -> None:  # noqa: WPS231
        """Runs the sync-experiment loop."""
        while self._is_in_progress:
            with logfire.span("Running defuser forward pass"):
                if not await self.api_queues.player_run(
                    experiment.defuser_uuid
                ).route.publish_with_ack(
                    RunForwardOnceCommand(), fail_after=PLAYER_TIMEOUT_SECONDS
                ):
                    logger.error("Defuser player took too long to respond")
                    raise PlayerTookTooLongError

            with logfire.span("Advancing time"):
                await self.api_queues.game_command(experiment.game_uuid).route.publish(
                    AdvanceTimeGameCommand()
                )
                await asyncio.sleep(SECONDS_PER_ACTION)

            if experiment.expert_uuid:
                with logfire.span("Running expert forward pass"):
                    if not await self.api_queues.player_run(
                        experiment.expert_uuid
                    ).route.publish_with_ack(
                        RunForwardOnceCommand(), fail_after=PLAYER_TIMEOUT_SECONDS
                    ):
                        logger.error("Expert player took too long to respond")  # noqa: WPS220
                        raise PlayerTookTooLongError  # noqa: WPS220

    async def async_experiment_loop(self, experiment: ExperimentDescriptor) -> None:
        """Runs the async-experiment loop."""

        async def _player_loop(uuid: UUID4, role: str) -> None:  # noqa: WPS430
            while self._is_in_progress:
                logger.info(f"Running {role} forward pass (async)")
                if not await self.api_queues.player_run(uuid).route.publish_with_ack(
                    RunForwardOnceCommand(), fail_after=PLAYER_TIMEOUT_SECONDS
                ):
                    # TODO: Change timeout for player as AI can take a while
                    raise PlayerTookTooLongError

        if experiment.expert_uuid:
            _ = await asyncio.gather(
                _player_loop(experiment.defuser_uuid, "defuser"),
                _player_loop(experiment.expert_uuid, "expert"),
            )
        else:
            _ = await asyncio.gather(_player_loop(experiment.defuser_uuid, "defuser"))

    @logfire.instrument("Stop Experiment ({hard_crash})")
    async def stop_experiment(self, *, hard_crash: bool) -> None:  # noqa: WPS213
        """Stop the currently running experiment."""
        if not (experiment := self._running_experiment):
            logger.warning("Tried to stop experiment when none are running")
            return

        logger.info(f"Stopping experiment, crashed: {hard_crash}")

        # Stop any running maguffs
        for task in self._running_experiment_tasks:
            _ = task.close()
        self._running_experiment_tasks.clear()

        await self.api_queues.experiment_done().route.publish(
            ExperimentDoneEvent(
                uuid=self.uuid,
                hard_crash=hard_crash,
                experiment_descriptor=self._running_experiment,
            )
        )

        # Stop players
        if hard_crash:
            final_player_command = StopExperimentCommand()
        else:
            final_game_state = await self.api_queues.game_command(
                experiment.game_uuid
            ).route.publish_with_response(
                GameGetObservationCommand(), fail_after=300, response_type=GameObservationResponse
            )

            if reflection_message := convert_bomb_state_to_reflection(final_game_state.bomb_state):
                # final_player_command = StopExperimentCommand()
                final_player_command = ReflectionCommand(reflection_message=reflection_message)
            else:
                logger.error(
                    f"Failed to generate reflection message from final bomb state: {final_game_state.bomb_state}"
                )
                final_player_command = StopExperimentCommand()

        player_stops = [
            self.api_queues.player_command(experiment.defuser_uuid).route.publish(
                final_player_command
            )
        ]
        if experiment.expert_uuid:
            player_stops.append(
                self.api_queues.player_command(experiment.expert_uuid).route.publish(
                    final_player_command
                )
            )

        _ = await asyncio.gather(*player_stops)

        # Stop Game
        await self.api_queues.game_command(experiment.game_uuid).route.publish(
            StopExperimentCommand()
        )

        # Remove the queue bindings
        await remove_experiment_bindings(experiment=experiment, api_queues=self.api_queues)
        self._running_experiment = None
        self._is_in_progress = False
        logger.info("Experiment stopped")
        await busy_wait_interval()
        await self.ready()
