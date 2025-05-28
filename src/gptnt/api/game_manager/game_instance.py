import asyncio
import os
from asyncio.exceptions import InvalidStateError
from contextlib import suppress
from dataclasses import dataclass, field
from functools import cached_property
from types import TracebackType
from typing import Any, override

import anyio
import logfire
from httpx._exceptions import HTTPError
from pydantic.main import BaseModel
from structlog import get_logger

from gptnt.api.base_em_client import BaseEMClient
from gptnt.api.base_rabbitmq_client import ExceptionUnhandledError
from gptnt.api.commands import (
    AdvanceTimeGameCommand,
    ConfigureGameCommand,
    GameCommand,
    GameDoneCommand,
    GameGetObservationCommand,
    PauseGameCommand,
    StopExperimentCommand,
    UnpauseGameCommand,
)
from gptnt.api.events import GameConnectEvent, NotReadyEvent, ReadyEvent
from gptnt.common.async_ops import busy_wait_interval, until
from gptnt.common.servers import get_available_port
from gptnt.ktane.actions import KtaneAction
from gptnt.ktane.client import KtaneClient, ObservationFrames
from gptnt.ktane.executable import get_executable_path
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.game import GameState

logger = get_logger()


class GameObservationResponse(BaseModel, frozen=True):
    """Response for the GameGetObservationCommand command."""

    observation_frames: ObservationFrames
    bomb_state: BombState


class GameProcessDiedError(Exception):
    """Exception indicating the game process has died."""


@dataclass(kw_only=True)
class GameInstance(BaseEMClient):
    """Manages an instance of a game.

    Supervises the game process and passes observations and actions to/from the RabbitMQ system.
    """

    _ktane_client: KtaneClient = field(init=False)
    _game_state: GameState = field(default=GameState.unknown, init=False)

    def __post_init__(self) -> None:
        """Synchronous startup logic to run BEFORE app start."""
        super().__post_init__()

        self.api_queues.game_actions(self.uuid).subscribe(self.handle_action)
        self.api_queues.game_command(self.uuid).subscribe(self.handle_command)
        self.api_queues.game_done(self.uuid).subscribe(self.handle_done)

        # Start invalid client to begin with
        self._ktane_client = KtaneClient(url="")

    @cached_property
    @override
    def connection_message(self) -> GameConnectEvent:
        """Specifies the connection message to send to the EM on startup."""
        return GameConnectEvent(uuid=self.uuid)

    @override
    async def lifespan_setup(self) -> None:
        """Asynchronous logic to run after app startup."""
        await super().lifespan_setup()

        logger.info(f"Started Game Instance with UUID: {self.uuid}")
        _ = self.background_tasks.create_task(self._run_game())
        _ = self.background_tasks.create_task(self._poll_game_state())

    @override
    @logfire.instrument("Cleanup Game")
    async def lifespan_cleanup(self) -> None:
        """Asynchronous logic to run during app shutdown."""
        self._kill_game_process()
        logger.info(f"Stopped Game Instance with UUID: {self.uuid}")

    @override
    async def handle_background_task_exception(
        self,
        exc_type: type[BaseException] | None = None,
        exc_obj: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        """Handle uncaught exceptions from background_tasks."""
        if exc_type is GameProcessDiedError:
            # Once the game is over, this is no longer a fatal error that needs to propegate to EM
            if self._game_state is not GameState.game_ended:
                await self.api_queues.experiment_ready().route.publish(
                    NotReadyEvent(uuid=self.uuid)
                )
            _ = self.background_tasks.create_task(self._run_game())

        elif exc_type is InvalidStateError:
            logger.warning("InvalidStateError occured")

        else:
            # Leave the error for parent to handle
            raise ExceptionUnhandledError

    async def handle_command(self, command: GameCommand) -> Any:
        """Handles a command from the Experiment Manager."""
        # TODO: Could replace with a switcher
        # TODO: Add error handling to the _ktane_client calls
        logger.info(f"Received command: {command}")

        if self._game_process.returncode is not None:
            return None

        if isinstance(command, StopExperimentCommand):
            self._kill_game_process()

        if isinstance(command, ConfigureGameCommand):
            await until(
                get_value=lambda: self._ktane_client.start_mission(command.mission_spec),
                target=True,
            )
            await until(get_value=lambda: self._game_state, target=GameState.lights_off)
            _ = await self._ktane_client.stop_time()

        if isinstance(command, PauseGameCommand):
            _ = await self._ktane_client.stop_time()

        if isinstance(command, UnpauseGameCommand):
            _ = await self._ktane_client.resume_time()

        if isinstance(command, AdvanceTimeGameCommand):
            _ = await self._ktane_client.advance_time()

        if isinstance(command, GameGetObservationCommand):
            # Timout to stop get_state calls after the game ends
            with suppress(TimeoutError):
                async with asyncio.timeout(30.0):
                    return await self._get_observation()
            return None

        return None

    async def handle_done(self, _: GameDoneCommand) -> None:
        """Only returns once the game is in a done state."""
        await until(get_value=lambda: self._game_state, target=GameState.transitioning)

    async def handle_action(self, action: KtaneAction) -> None:
        """Handles an action sent via the action queue."""
        if self._game_process.returncode is None:
            logger.debug("Game process is still running.")

        if not await self._ktane_client.healthcheck():
            logger.error("Game failed healhcheck")
            return

        _ = await self._ktane_client.send_action(action=action)

    def _kill_game_process(self) -> None:
        """Kills the game process."""
        with suppress(AttributeError):
            if self._game_process.returncode is None:
                self._game_process.kill()

    async def _poll_game_state(self) -> None:
        """Polls the state of the game."""
        while True:  # noqa: WPS457
            await busy_wait_interval()

            if not self._is_game_alive():
                continue

            with suppress(HTTPError):
                with logfire.suppress_instrumentation():
                    new_state = await self._ktane_client.gamestate()
                if new_state is not self._game_state:
                    logger.info(f"Game state changed: {self._game_state} -> {new_state}")
                    self._game_state = new_state

    async def _run_game(self) -> None:
        """Runs a game until it crashes or exits."""
        with logfire.span("Start game"):
            # Start a new game instance and connect a ktane client
            self._game_process = await anyio.open_process(
                cwd=get_executable_path().parent,
                command=[get_executable_path()],
                env={"port": str(game_server_port := get_available_port())} | os.environ.copy(),
            )
            logger.info(f"Game started on port: {game_server_port}")
            await self._ktane_client.update_url(f"http://localhost:{game_server_port}")
            self._game_state = GameState.unknown

        # The following all run at the same time and are handled as they finish
        main_menu = self.background_tasks.create_task(
            until(get_value=lambda: self._game_state, target=GameState.main_menu)
        )
        game_dead = self.background_tasks.create_task(
            until(get_value=lambda: self._game_process.returncode is not None, target=True)
        )
        async for finished in asyncio.as_completed([main_menu, game_dead]):
            if finished is main_menu:
                await self.api_queues.experiment_ready().route.publish(ReadyEvent(uuid=self.uuid))
            if finished is game_dead:
                _ = main_menu.cancel()
                _ = game_dead.cancel()
                raise GameProcessDiedError

    def _is_game_alive(self) -> bool:
        """Checks if the game process is alive."""
        with suppress(AttributeError):
            return self._game_process.returncode is None
        return False

    async def _get_observation(self) -> GameObservationResponse:
        """Gets the current observation from the game."""
        while await self._ktane_client.get_state() is None:
            logger.debug("Waiting for bomb state to be available")
            await busy_wait_interval()

        frames, state = await asyncio.gather(
            self._ktane_client.get_observation_frames(), self._ktane_client.get_state()
        )
        assert state is not None, "Bomb state should not be None"
        logger.debug("Received observation frames and bomb state from game")
        return GameObservationResponse(observation_frames=frames, bomb_state=state)
