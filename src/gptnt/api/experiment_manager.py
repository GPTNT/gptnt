import asyncio
import itertools
from collections.abc import Callable
from types import TracebackType
from typing import Any, Self

import logfire
from structlog import get_logger

from gptnt.api.player_client import SupervisedPlayerClient
from gptnt.api.room_client import SupervisedRoomManagerClient
from gptnt.api.structures import RoomStage
from gptnt.ktane.experiments.experiments import ExperimentSpec
from gptnt.ktane.experiments.pairing import Pairing
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.modules import KtaneComponent

_logger = get_logger()


# TODO: Generics!
async def until(get_value: Callable[[], Any], target: Any) -> None:
    """Await until a value (specified by passed getter) becomes the target."""
    while get_value() is not target:  # noqa: ASYNC110
        await asyncio.sleep(1)


class ExperimentManager:
    """Manages a set of experiments.

    Requires players and rooms to join.
    """

    def __init__(self) -> None:
        # Control and status
        self._should_exit: bool = False
        self._tasks: list[asyncio.Task[None]] = []

        # Connection Tracking
        self.players: list[SupervisedPlayerClient] = []
        self.rooms: list[SupervisedRoomManagerClient] = []

    async def __aenter__(self) -> Self:
        """Starts the ExperimentManager."""
        self._tasks.append(asyncio.create_task(coro=self._main_loop()))
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        """Stops the ExperimentManager."""
        self._should_exit = True
        for task in self._tasks:
            _ = task.cancel()

    async def start_available_experiments(self) -> None:
        """Starts all ExperimentConfig's that have the correct players and rooms available."""
        # TODO: Make this actually run proper configs, this currently just throws the first
        # room/players it finds with a random config

        # Filter for available clients (running, connected, and not in an experiment already)
        available_players = [
            player for player in self.players if player.is_running and not player.in_experiment
        ]

        available_rooms = [
            room
            for room in self.rooms
            if room.is_running
            and not room.in_experiment
            and room.state is RoomStage.ready_for_config
        ]

        _logger.info(
            f"Available Players: {len(available_players)}/{len(self.players)}, Available Rooms: {len(available_rooms)}/{len(self.rooms)}"
        )

        # TODO: Make this find the correct pairings
        if len(available_players) >= 2 and len(available_rooms) >= 1:  # noqa: PLR2004
            expert = available_players.pop()
            defuser = available_players.pop()
            room = available_rooms.pop()

            expert.in_experiment = True
            defuser.in_experiment = True
            room.in_experiment = True

            # Move players into the room
            _logger.info("Sending players to room")
            _ = await asyncio.gather(
                expert.client.join_room(room=room.metadata),
                defuser.client.join_room(room=room.metadata),
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
            for client in itertools.chain(self.players, self.rooms):
                if not client.is_running:
                    _ = await client.start()  # noqa: WPS476
                    self._tasks.append(asyncio.create_task(coro=client.supervisor_loop()))

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
        self,
        expert: SupervisedPlayerClient,
        defuser: SupervisedPlayerClient,
        room: SupervisedRoomManagerClient,
        spec: ExperimentSpec,
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
    async def _parallel_experiment(
        self,
        expert: SupervisedPlayerClient,
        defuser: SupervisedPlayerClient,
        room: SupervisedRoomManagerClient,
    ) -> None:
        """Runs an experiment where both players can act at the same time."""
        _ = await asyncio.gather(expert.client.run_for_game(), defuser.client.run_for_game())

        while room.state is not RoomStage.done:
            if (not room.is_running) or (not expert.is_running) or (not defuser.is_running):
                # TODO: Error handling
                raise NotImplementedError
            await asyncio.sleep(1)

        await self._end_experiment(expert, defuser, room)

    @logfire.instrument("Run Sequential experiment")
    async def _sequential_experiment(
        self,
        expert: SupervisedPlayerClient,
        defuser: SupervisedPlayerClient,
        room: SupervisedRoomManagerClient,
    ) -> None:
        """Runs an experiment where players take turns."""
        while room.state is not RoomStage.done:
            _ = await expert.client.run_for_turn()
            _ = await defuser.client.run_for_turn()

            if (not room.is_running) or (not expert.is_running) or (not defuser.is_running):
                # TODO: Error handling
                raise NotImplementedError
            await asyncio.sleep(1)

        await self._end_experiment(expert, defuser, room)

    @logfire.instrument("End experiment")
    async def _end_experiment(
        self,
        expert: SupervisedPlayerClient,
        defuser: SupervisedPlayerClient,
        room: SupervisedRoomManagerClient,
    ) -> None:
        """Performs the finishing logic for an experiment."""
        _ = await room.client.reset_room()
        _ = await asyncio.gather(expert.client.stop_experiment(), defuser.client.stop_experiment())
        _logger.info("Done resetting")

        expert.in_experiment = False
        defuser.in_experiment = False
        room.in_experiment = False
