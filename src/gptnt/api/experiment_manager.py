import asyncio
import itertools
import uuid
from collections.abc import Callable
from typing import Any

import logfire
from structlog import get_logger

from gptnt.api.player_client import SupervisedPlayerClient
from gptnt.api.room_client import SupervisedRoomManagerClient
from gptnt.api.structures import GameMetadata, RoomStage
from gptnt.api.tinder import get_playable_pairings
from gptnt.ktane.experiments.experiments import ExperimentSpec

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
        self.should_exit: bool = False
        self.tasks: list[asyncio.Task[None]] = []

        # Experiments
        self.experiments: set[ExperimentSpec] = set()

        # Connection Tracking
        self.players: list[SupervisedPlayerClient] = []
        self.rooms: list[SupervisedRoomManagerClient] = []

    def get_available_rooms(self) -> list[SupervisedRoomManagerClient]:
        """Returns a list of all available rooms."""
        return [
            room
            for room in self.rooms
            # Ensure room is running and not in an experiment
            if room.is_running
            and not room.in_experiment
            # And also ensure the room is waiting for a config
            and room.state is RoomStage.ready_for_config
        ]

    def get_available_players(self) -> set[SupervisedPlayerClient]:
        """Returns a list of all available players."""
        return {
            player
            for player in self.players
            # Ensure player is running and not in an experiment
            if player.is_running and not player.in_experiment
        }

    # Experiment logic
    async def main_loop(self) -> None:
        """Runs the main logic for the Experiment Manager.

        Culls dead connections and supervisors. Starts new experiments when valid pairings are
        found. BUG: Dead connections not culled.
        """
        while not self.should_exit:
            # Start newly connected clients and their supervisors
            for client in itertools.chain(self.players, self.rooms):
                if not client.is_running:
                    _ = await client.start()  # noqa: WPS476
                    self.tasks.append(asyncio.create_task(coro=client.supervisor_loop()))

            # Start experiments that have valid pairings available
            await self.start_available_experiments()

            # Clear any finished tasks
            self.tasks = [task for task in self.tasks if not task.done()]

            # Short delay to let the system breathe
            await asyncio.sleep(1)

    async def start_available_experiments(self) -> None:
        """Starts all ExperimentConfig's that have the correct players and rooms available."""
        available_rooms = self.get_available_rooms()
        available_players = self.get_available_players()
        if not available_rooms or not available_players:
            # No rooms or players available, nothing to do
            return

        # Start all available experiments as long as there are enough rooms
        available_pairings = get_playable_pairings(
            available_players=available_players, available_experiments=self.experiments
        )
        if not available_pairings:
            # No available pairings, nothing to do
            return

        for expert, defuser, spec in available_pairings:
            if not available_rooms:
                # No more rooms, can't start any more pairings
                return
            room = available_rooms.pop()

            expert.in_experiment = True
            defuser.in_experiment = True
            room.in_experiment = True
            self.experiments.remove(spec)

            _ = await asyncio.gather(  # noqa: WPS476
                expert.client.join_room(room=room.metadata),
                defuser.client.join_room(room=room.metadata),
            )
            self.tasks.append(
                asyncio.create_task(
                    coro=self._start_experiment(
                        expert=expert, defuser=defuser, room=room, spec=spec
                    )
                )
            )

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
        game_id = uuid.uuid4()

        _ = await asyncio.gather(
            room.client.configure_experiment(config=spec.mission_spec),
            expert.client.start_experiment(
                game_metadata=GameMetadata(
                    experiment_spec=spec, player_metadata=expert.metadata, game_id=game_id
                )
            ),
            defuser.client.start_experiment(
                game_metadata=GameMetadata(
                    experiment_spec=spec, player_metadata=defuser.metadata, game_id=game_id
                )
            ),
        )

        # Start game and switch to correct communication style
        await until(get_value=lambda: room.state, target=RoomStage.ready_for_start)
        _ = await room.client.start_experiment()

        match spec.communication_style:
            case "parallel":
                await self._parallel_experiment(
                    expert=expert, defuser=defuser, room=room, spec=spec
                )
            case "sequential":
                await self._sequential_experiment(
                    expert=expert, defuser=defuser, room=room, spec=spec
                )

    @logfire.instrument("Run parallel experiment")
    async def _parallel_experiment(
        self,
        expert: SupervisedPlayerClient,
        defuser: SupervisedPlayerClient,
        room: SupervisedRoomManagerClient,
        spec: ExperimentSpec,
    ) -> None:
        """Runs an experiment where both players can act at the same time."""
        _logger.info("Starting parallel experiment")
        _ = await asyncio.gather(expert.client.run_for_game(), defuser.client.run_for_game())

        while room.state is not RoomStage.done:
            if (not room.is_running) or (not expert.is_running) or (not defuser.is_running):
                # If the experiment fails, it needs to run again, but we still want metrics
                _logger.error("Something died, stopping experiment and returning to the pool")
                self.experiments.add(spec)
                break

            await asyncio.sleep(1)

        await self._end_experiment(expert, defuser, room)

    @logfire.instrument("Run Sequential experiment")
    async def _sequential_experiment(
        self,
        expert: SupervisedPlayerClient,
        defuser: SupervisedPlayerClient,
        room: SupervisedRoomManagerClient,
        spec: ExperimentSpec,
    ) -> None:
        """Runs an experiment where players take turns."""
        _logger.info("Starting sequential experiment")
        while room.state is not RoomStage.done:
            _ = await expert.client.run_for_turn()
            _ = await defuser.client.run_for_turn()

            # BUG: This does not run often enough
            if (not room.is_running) or (not expert.is_running) or (not defuser.is_running):
                # If the experiment fails, it needs to run again, but we still want metrics
                _logger.error("Something died, stopping experiment and returning to the pool")
                self.experiments.add(spec)
                break

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
        _logger.info("Experiment finished, resetting room and players")
        _ = await room.client.reset_room()
        _ = await asyncio.gather(expert.client.stop_experiment(), defuser.client.stop_experiment())

        expert.in_experiment = False
        defuser.in_experiment = False
        room.in_experiment = False
