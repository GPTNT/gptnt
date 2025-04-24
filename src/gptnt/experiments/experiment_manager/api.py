import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from itertools import chain
from types import TracebackType
from typing import Any, Self, override

import httpx
import logfire
import uvicorn
from fastapi import APIRouter, FastAPI
from structlog import get_logger

from gptnt.api.player_client import PlayerClient
from gptnt.api.room_client import RoomManagerClient
from gptnt.api.structures import PlayerAPIInfo, RoomManagerAPIInfo, RoomStage
from gptnt.ktane.experiments.experiments import ExperimentSpec
from gptnt.ktane.experiments.pairing import Pairing
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.modules import KtaneComponent

_logger = get_logger()


@dataclass
class SupervisedClient[
    InfoT: PlayerAPIInfo | RoomManagerAPIInfo,
    ClientT: PlayerClient | RoomManagerClient,
]:
    """Client with a supervisor to perform health checks on the connection."""

    info: InfoT  # noqa: WPS110
    client: ClientT
    is_connected: bool = True
    is_started: bool = False
    in_experiment: bool = False

    _supervisor_interval: float = 0.5

    async def start(self) -> None:
        """Starts the client."""
        self.is_started = True
        _ = await self.client.start()

    async def stop(self) -> None:
        """Stops the client."""
        self.is_connected = False
        _ = await self.client.stop()

    async def supervisor(self) -> None:
        """Returns the supervisor co-routine for this client."""
        raise NotImplementedError


class Player(SupervisedClient[PlayerAPIInfo, PlayerClient]):
    """Information about connected PlayerAPI."""

    @override
    async def supervisor(self) -> None:
        """Returns the supervisor co-routine for this client."""
        while self.is_started:
            if not await self.client.healthcheck():
                break
            await asyncio.sleep(self._supervisor_interval)
        _logger.info("Player died")
        self.is_connected = False
        await self.stop()


class Room(SupervisedClient[RoomManagerAPIInfo, RoomManagerClient]):
    """Information about connected RoomManagerAPI."""

    state: RoomStage = RoomStage.boot

    @override
    async def supervisor(self) -> None:
        """Returns the supervisor co-routine for this client."""
        while self.is_started:
            try:
                self.state = await self.client.statecheck()
            except httpx.HTTPError:
                break
            await asyncio.sleep(self._supervisor_interval)
        self.is_connected = False
        await self.stop()


# TODO: Generics!
async def until(get_value: Callable[[], Any], target: Any) -> None:
    """Await until a value (specified by passed getter) becomes the target."""
    while get_value() is not target:  # noqa: ASYNC110
        await asyncio.sleep(1)


class ExperimentManagerAPI:
    """Manages a set of experiments.

    Requires players and rooms to join.
    """

    def __init__(self) -> None:
        # Add endpoints to app
        self.app = FastAPI()
        self._router = APIRouter()
        self._router.add_api_route(path="/health", endpoint=self._health_endpoint, methods=["GET"])
        self._router.add_api_route(
            path="/connect-player", endpoint=self._connect_player_endpoint, methods=["POST"]
        )
        self._router.add_api_route(
            path="/connect-room", endpoint=self._connect_room_endpoint, methods=["POST"]
        )
        self.app.include_router(router=self._router)

        self._fastapi_server: uvicorn.Server
        self._fastapi_server_port: int
        self._fastapi_server_task: asyncio.Task[None]

        # Control and status
        self._should_exit: bool = False
        self._tasks: list[asyncio.Task[None]] = []

        # Connection Tracking
        self.players: list[Player] = []
        self.rooms: list[Room] = []

    async def __aenter__(self) -> Self:
        """Starts the ExperimentManager."""
        self._fastapi_server_port = 8099
        self._fastapi_server = uvicorn.Server(
            config=uvicorn.Config(
                app=self.app, port=self._fastapi_server_port, log_level="warning"
            )
        )
        self._tasks.append(asyncio.create_task(coro=self._fastapi_server.serve()))
        self._tasks.append(asyncio.create_task(coro=self._main_loop()))
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        """Stops the ExperimentManager."""
        _ = await self._fastapi_server.shutdown()

        self._should_exit = True
        for task in self._tasks:
            _ = task.cancel()

    async def start_available_experiments(self) -> None:
        """Starts all ExperimentConfig's that have the correct players and rooms available."""
        # TODO: Make this actually run proper configs, this currently just throws the first
        # room/players it finds with a random config

        # Filter for available clients (running, connected, and not in an experiment already)
        available_players: list[Player] = [
            player
            for player in self.players
            if player.is_started and player.is_connected and not player.in_experiment
        ]
        available_rooms: list[Room] = [
            room
            for room in self.rooms
            if room.is_started
            and room.is_connected
            and not room.in_experiment
            and room.state is RoomStage.ready_for_config
        ]

        # _logger.info(
        #     f"Available Players: {len(available_players)}, Available Rooms: {len(available_rooms)}"
        # )

        # TODO: Make this find the correct pairings
        if len(available_players) >= 2 and len(available_rooms) >= 1:  # noqa: PLR2004
            expert: Player = available_players.pop()
            defuser: Player = available_players.pop()
            room: Room = available_rooms.pop()

            expert.in_experiment = True
            defuser.in_experiment = True
            room.in_experiment = True

            # Move players into the room
            # `asyncio.gather` does the moves in parallel
            _logger.info("Gathering")
            _ = await asyncio.gather(
                expert.client.join_room(room=room.info), defuser.client.join_room(room=room.info)
            )
            _logger.info("Gathering")

            # Start the game
            # TODO: Pass in an actual spec
            self._tasks.append(
                asyncio.create_task(
                    coro=self._start_experiment(
                        expert=expert,
                        defuser=defuser,
                        room=room,
                        spec=ExperimentSpec(
                            mission_spec=KtaneMissionSpec(
                                seed=1000,
                                time_limit=300,  # noqa: WPS432
                                optional_widgets=0,
                                components=[KtaneComponent.big_button],
                            ),
                            pairing=Pairing(
                                defuser="dont care",
                                expert="also dont care",
                                pairing_type="pairwise",
                            ),
                            communication_style="parallel",
                            condition="single_module",
                        ),
                    )
                )
            )

    # Experiment logic
    async def _main_loop(self) -> None:
        """Runs the main logic for the Experiment Manager.

        Culls dead connections and supervisors. Starts new experiments when valid pairings are
        found.
        """
        while not self._should_exit:
            # Start newly connected clients and their supervisors
            for client in chain(self.players, self.rooms):
                if not client.is_started:
                    await client.start()  # noqa: WPS476
                    self._tasks.append(asyncio.create_task(coro=client.supervisor()))

            _logger.debug(f"P: {len(self.players)}, R:{len(self.rooms)}")

            # Remove dead clients
            # BUG: This breaks the connecting logic somehow?
            # self.players = list(filter(lambda p: p.is_connected, self.players))
            # self.rooms = list(filter(lambda r: r.is_connected, self.rooms))

            _logger.debug(f"P: {len(self.players)}, R:{len(self.rooms)}")

            # Start experiments that have valid pairings available
            await self.start_available_experiments()
            # Clear any finished tasks
            self._tasks = [task for task in self._tasks if not task.done()]
            # Short delay to let the system breathe
            _logger.debug("Main Loop")
            await asyncio.sleep(1)

        _logger.info("Exited main loop")

    @logfire.instrument("Start experiment")
    async def _start_experiment(  # noqa: WPS217
        self, expert: Player, defuser: Player, room: Room, spec: ExperimentSpec
    ) -> None:
        """Performs the starting logic for an experiment, then switches to seq/par impl."""
        # Configure the experiment
        await until(get_value=lambda: room.state, target=RoomStage.ready_for_config)
        _ = await room.client.configure_experiment(config=spec.mission_spec)

        # Start game and switch to correct communication style
        await until(get_value=lambda: room.state, target=RoomStage.ready_for_start)
        _ = await room.client.start_experiment()

        match spec.communication_style:
            case "parallel":
                await self._parallel_experiment(expert=expert, defuser=defuser, room=room)
            case "sequential":
                await self._sequential_experiment(expert=expert, defuser=defuser, room=room)

    @logfire.instrument("Run Parallel experiment")
    async def _parallel_experiment(self, expert: Player, defuser: Player, room: Room) -> None:
        """Runs an experiment where both players can act at the same time."""
        _ = await asyncio.gather(expert.client.run_for_game(), defuser.client.run_for_game())

        while room.state is not RoomStage.done:
            if (not room.is_connected) or (not expert.is_connected) or (not defuser.is_connected):
                # TODO: Error handling
                raise NotImplementedError
            await asyncio.sleep(1)

        await self._end_experiment(expert, defuser, room)

    @logfire.instrument("Run Sequential experiment")
    async def _sequential_experiment(self, expert: Player, defuser: Player, room: Room) -> None:
        """Runs an experiment where players take turns."""
        while room.state is not RoomStage.done:
            _ = await expert.client.run_for_turn()
            _ = await defuser.client.run_for_turn()

            if (not room.is_connected) or (not expert.is_connected) or (not defuser.is_connected):
                # TODO: Error handling
                raise NotImplementedError
            await asyncio.sleep(1)

        await self._end_experiment(expert, defuser, room)

    @logfire.instrument("End experiment")
    async def _end_experiment(self, expert: Player, defuser: Player, room: Room) -> None:
        """Performs the finishing logic for an experiment."""
        _ = await room.client.reset_room()
        _ = await asyncio.gather(expert.client.stop_experiment(), defuser.client.stop_experiment())
        _logger.info("Done resetting")

        expert.in_experiment = False
        defuser.in_experiment = False
        room.in_experiment = False

    # Endpoints
    def _connect_player_endpoint(self, player_info: PlayerAPIInfo) -> None:
        """Handles a new player connecting to the experiment manager."""
        self.players.append(
            Player(info=player_info, client=PlayerClient(url=player_info.fastapi_url))
        )

    @logfire.instrument("Connect room")
    def _connect_room_endpoint(self, room_info: RoomManagerAPIInfo) -> None:
        """Handles a new room connecting to the experiment manager."""
        self.rooms.append(Room(info=room_info, client=RoomManagerClient(room_info.fastapi_url)))

    def _health_endpoint(self) -> None:
        """Empty endpoint used for externally polling if the ExperimentManager is still running."""
        return  # noqa: WPS324
