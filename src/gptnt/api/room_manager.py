import asyncio
import os
import uuid
from contextlib import suppress
from types import TracebackType
from typing import TYPE_CHECKING, Self

import anyio
import httpx
import logfire
from structlog import get_logger

from gptnt.api.experiment_manager_client import ExperimentManagerClient
from gptnt.api.structures import RoomMetadata, RoomStage
from gptnt.common.async_ops import healthcheck_interval
from gptnt.common.servers import get_available_port, httpx_create_async_client
from gptnt.dialogue_space.server import DialogueSpaceServer
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.executable import get_executable_path
from gptnt.ktane.state.game import GameState

if TYPE_CHECKING:
    from asyncio.tasks import Task

    from anyio.abc import Process

_logger = get_logger()

game_crash_counter = logfire.metric_counter(
    "game_crash_count", description="Number of times the game crashed"
)
game_health_fail_counter = logfire.metric_counter(
    "game_health_fail_count", description="Number of times the game failed a healthcheck"
)
room_restart_counter = logfire.metric_counter(
    "room_restart_count", description="Number of times the room was restarted"
)
em_health_fail_counter = logfire.metric_counter(
    "em_health_fail_count", description="Number of restarts because the EM failed the healthcheck"
)


class RoomManager:
    """Manages a game "room".

    Starts the game, dialogue space, and waits for players.
    """

    def __init__(self, *, hostname: str, port: int) -> None:
        self.hostname = hostname

        self._fastapi_server_port: int = port

        self._players_per_game: int = 2
        self._uuid = uuid.uuid4()

        # Control and status flags
        self.lifecycle_stage: RoomStage
        self.game_state: GameState
        self._state_changed: asyncio.Event
        self._players_connected: asyncio.Event
        self._experiment_manager_connected: asyncio.Event

        self._should_exit: bool = True
        self._restart_raised: asyncio.Event
        self.reset_raised: asyncio.Event

        self._permanent_tasks: list[Task[None]] = []
        self._restartable_tasks: list[Task[None]] = []

        # Sub services
        self._fastapi_supervisor_client: httpx.AsyncClient

        self._game_process: Process

        self._dialogue_space_server: DialogueSpaceServer
        self.ktane_client: KtaneClient
        self._experiment_manager_client: ExperimentManagerClient

    @property
    def url(self) -> str:
        """The base URL of the API."""
        return f"http://{self.hostname}:{self._fastapi_server_port}"

    @property
    def room_info(self) -> RoomMetadata:
        """Build the room info for the experiment manager."""
        return RoomMetadata(
            fastapi_url=self.url,
            dialogue_space_url=self._dialogue_space_server.url,
            ktane_url=f"{self.ktane_client.client.base_url}",
            state=self.lifecycle_stage,
            uuid=self._uuid,
        )

    def kill_game_process(self) -> None:
        """Kill the game process.

        This is a workaround for the fact that the game process is not killed when the RoomManager
        is stopped.
        """
        if self._game_process.returncode is None:
            self._game_process.kill()
            _logger.info("Game process killed")

    # Context Management
    async def __aenter__(self) -> Self:
        """Enters async context, fully starting the RoomManager."""
        self._should_exit = False

        # `self._reset_loop` task will start services and supervisors
        # This ensures that a running task always owns DialogueSpaceServer,
        # KtaneClient, EMClient, and the FastAPI supervisor client
        self._permanent_tasks.append(asyncio.create_task(coro=self._restart_loop()))
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        """Exit async context, fully and cleanly closing the RoomManger."""
        self._should_exit = True
        for task in self._permanent_tasks:
            _ = task.cancel()
        await self.stop()

    async def start(self, *, start_subservices: bool = True) -> None:
        """Starts the subservices and supervisors."""
        self.lifecycle_stage = RoomStage.boot
        self.game_state = GameState.unknown

        self._state_changed = asyncio.Event()
        self._players_connected = asyncio.Event()
        self._experiment_manager_connected = asyncio.Event()
        self._restart_raised = asyncio.Event()
        self.reset_raised = asyncio.Event()

        with logfire.span("Start room manager", room=self._uuid):
            if start_subservices:
                await self._start_subservices()

            await self._start_supervisors()
        self._restartable_tasks.append(asyncio.create_task(coro=self._lifecycle_loop()))

    async def stop(self, *, stop_subservices: bool = True) -> None:
        """Cleanly stops any running subservices and supervisors."""
        with logfire.span("Stop room manager", room=self._uuid):
            for task in self._restartable_tasks:
                _ = task.cancel()
            self._restartable_tasks = []
            await self._stop_supervisors()

            if stop_subservices:
                if self._game_process.returncode is None:
                    self._game_process.kill()
                await self._stop_subservices()

    # Sub-service handlers
    async def _restart_loop(self) -> None:  # noqa: WPS213, WPS217
        """Restarts the RoomManager when the restart flag is raised by a supervisor.

        Runs forever once started, is the root task which owns all others.
        """
        await self.start()

        while not self._should_exit:
            _ = await asyncio.wait(
                fs=[
                    asyncio.create_task(coro=self._restart_raised.wait()),
                    asyncio.create_task(coro=self.reset_raised.wait()),
                ],
                return_when="FIRST_COMPLETED",
            )

            if self._restart_raised.is_set():
                room_restart_counter.add(1)
                with logfire.span("Restarting room"):
                    _logger.error("RoomManager restarting")
                    await self.stop()
                    await self.start()
                    self._restart_raised.clear()

            elif self.reset_raised.is_set():
                with logfire.span("Resetting room"):
                    # Resume the game if need be and wait for it to resume
                    _ = await self.ktane_client.resume_time()
                    await asyncio.sleep(4)
                    await self.stop(stop_subservices=False)
                    _ = await self.ktane_client.reset()
                    self._dialogue_space_server.reset()
                    await self.start(start_subservices=False)
                    self.reset_raised.clear()

    async def _lifecycle_loop(self) -> None:  # noqa: WPS217, WPS213
        """Moves the RoomManager through the lifecycle.

        Restarts on resets and restarts.
        """

        @logfire.instrument("Wait for game state: {target_state=}")
        async def _until_game_state(target_state: GameState) -> None:  # noqa: WPS430
            """Waits until a specific GameState is reached."""
            while self.game_state is not target_state:
                _ = await self._state_changed.wait()
                self._state_changed.clear()

        with logfire.span("Loading game", room=self._uuid):
            self.lifecycle_stage = RoomStage.boot

            await _until_game_state(target_state=GameState.main_menu)
            self.lifecycle_stage = RoomStage.ready_for_config

        with logfire.span("Waiting for players", room=self._uuid):
            await _until_game_state(target_state=GameState.lights_off)
            _ = await self.ktane_client.stop_time()  # BUG: This might fail
            _ = await self._players_connected.wait()
            self._players_connected.clear()
            self.lifecycle_stage = RoomStage.ready_for_start

        with logfire.span("Waiting for game to start", room=self._uuid):
            await _until_game_state(target_state=GameState.lights_on)
            self.lifecycle_stage = RoomStage.in_experiment

        with logfire.span("Waiting for game to end", room=self._uuid):
            await _until_game_state(target_state=GameState.game_ended)
            self.lifecycle_stage = RoomStage.done

    @logfire.instrument("Start subservices")
    async def _start_subservices(self) -> None:
        """Start the server and app."""
        # 1. start the game in the room
        game_server_port = get_available_port()
        _logger.info("Starting `KTANE` (as subprocess)", port=game_server_port)
        self._game_process = await anyio.open_process(
            cwd=get_executable_path().parent,
            command=[get_executable_path()],
            env={"port": str(game_server_port)} | os.environ.copy(),
        )
        # 2. start the dialogue space server
        ds_server_port = get_available_port()
        _logger.info("Starting `DialogueSpaceServer`", port=ds_server_port)
        self._dialogue_space_server = await DialogueSpaceServer.from_host_and_port(
            host=self.hostname, port=ds_server_port
        ).start()

        # 3. Start the ktane client
        _logger.info("Starting `KtaneClient`", port=game_server_port)
        self.ktane_client = await KtaneClient(
            url=f"http://{self.hostname}:{game_server_port}"
        ).__aenter__()

        # 4. Start the experiment manager client
        _logger.info("Starting `ExperimentManagerClient`", port=8099)  # noqa: WPS432
        self._experiment_manager_client = await ExperimentManagerClient(
            url="http://localhost:8099"
        ).start()

        self._permanent_tasks.append(
            asyncio.create_task(coro=self._supervise_experiment_manager_client())
        )

    @logfire.instrument("Stop subservices")
    async def _stop_subservices(self) -> None:  # noqa: WPS213
        """Cleanly stop all of the sub-services and sub-service supervisors."""
        # Close DialogueSpaceServer first to stop players from playing
        _logger.info("Stopping `DialogueSpaceServer`", url=self._dialogue_space_server.url)
        await self._dialogue_space_server.__aexit__()

        _logger.info("Stopping `KTANE` (as subprocess)", url=self.ktane_client.client.base_url)
        if self._game_process.returncode is None:
            self._game_process.terminate()

        _logger.info("Stopping `KtaneClient`", url=self.ktane_client.client.base_url)
        await self.ktane_client.__aexit__()

        _logger.info("Stopping `ExperimentManagerClient`", url=self._experiment_manager_client.url)
        await self._experiment_manager_client.stop()

    async def _start_supervisors(self) -> None:
        """Starts the sub-service supervisors."""
        self._fastapi_supervisor_client = await httpx_create_async_client(
            base_url=f"http://{self.hostname}:{self._fastapi_server_port}"
        ).__aenter__()
        self._restartable_tasks.extend(
            [
                asyncio.create_task(coro=self._supervise_fastapi_server()),
                asyncio.create_task(coro=self._supervise_game_process()),
                asyncio.create_task(coro=self._supervise_dialogue_space_server()),
                asyncio.create_task(coro=self._supervise_ktane_client()),
            ]
        )

    async def _stop_supervisors(self) -> None:
        """Cleanly stops all sub-service supervisors."""
        await self._fastapi_supervisor_client.__aexit__()

    # Subservice supervisors
    async def _supervise_fastapi_server(self) -> None:
        """Supervises the FastAPI server.

        Triggers a reset if the internal FastAPI server stops responding to healthchecks.
        """
        _logger.info("Starting FastAPI supervisor")
        while not self._restart_raised.is_set():
            try:
                _ = (await self._fastapi_supervisor_client.get(url="/health")).raise_for_status()
            except httpx.HTTPError:
                _logger.exception("FastAPI server failed healthcheck")
                self._restart_raised.set()

            await healthcheck_interval()

    async def _supervise_game_process(self) -> None:
        """Supervises the Game subprocess.

        Triggers a reset if the game sub-process ever exits. (game closes or crashes)
        """
        _logger.info("Starting game sub-process supervisor")
        while not self._restart_raised.is_set():
            if self._game_process.returncode is not None:
                _logger.exception("Game sub-process exited unexpectedly")
                game_crash_counter.add(1)
                self._restart_raised.set()

            await healthcheck_interval()

    async def _supervise_dialogue_space_server(self) -> None:
        """Supervises the DialogueSpaceServer.

        Wait until the correct number of players connect then trigger a reset if a player
        disconnects from the dialogue space during an experiment.
        """
        # Wait for players to connect
        while not self._should_exit:
            if self._dialogue_space_server.active_connections == self._players_per_game:
                self._players_connected.set()
                break

            await healthcheck_interval()

    async def _supervise_ktane_client(self) -> None:  # noqa: WPS231, WPS213
        """Supervises the KtaneClient.

        Waits until the game server first connects, then triggers a failure if it ever fails a
        healthcheck.
        """
        _logger.info("Starting KtaneClient supervisor")

        # Wait for the GameServer to connect
        _logger.info("Waiting for KtaneClient to connect to game server")
        with logfire.suppress_instrumentation():
            while not self._should_exit:
                with suppress(httpx.HTTPError, TimeoutError):
                    if await self.ktane_client.healthcheck(skip_logger=True):
                        break  # noqa: WPS220

        _logger.info("KtaneClient connected to game server")
        while not self._restart_raised.is_set():
            # See if the game server is still alive
            try:
                with logfire.suppress_instrumentation():
                    new_game_state = await self.ktane_client.gamestate()

            # If it's not alive, raise an exception
            except (httpx.HTTPError, TimeoutError):
                _logger.exception("Ktane failed healthcheck")
                game_health_fail_counter.add(1)
                self._restart_raised.set()

            # If it is alive, check and set the game state
            else:
                if new_game_state != self.game_state:
                    _logger.info(
                        "Game state changed",
                        old_state=self.game_state.name,
                        new_state=new_game_state.name,
                    )
                    self.game_state = new_game_state
                self._state_changed.set()

            await healthcheck_interval()

    async def _supervise_experiment_manager_client(self) -> None:
        """Supervises the connection to the experiment manager.

        Closes the RoomManager if the experiment manager stops responding to healthchecks. (This
        either signals the end of experiments, or a total system failure)"
        """
        _logger.info("Starting ExperimentManager supervisor")

        # Wait for the ExperimentManager to connect
        with logfire.suppress_instrumentation():
            while not self._should_exit:
                if await self._experiment_manager_client.wait_for_valid_healthcheck():
                    break

        # Connect self and monitor connection
        # TODO: This might not work (maybe bugged)
        _logger.info("Connecting room to ExperimentManager")
        _ = await self._experiment_manager_client.connect_room(connection=self.room_info)
        with logfire.suppress_instrumentation():
            while not self._should_exit:
                if not await self._experiment_manager_client.healthcheck():
                    _logger.error("ExperimentManager failed healthcheck")
                    em_health_fail_counter.add(1)
                    self._restart_raised.set()
                    break

                await healthcheck_interval()
