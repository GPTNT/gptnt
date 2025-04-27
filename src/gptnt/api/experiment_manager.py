import asyncio
import itertools
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import logfire
from pydantic import UUID4
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


@dataclass
class ExperimentMetadata:
    """Information about a single experiment (game/session)."""

    expert: SupervisedPlayerClient
    defuser: SupervisedPlayerClient
    room: SupervisedRoomManagerClient
    spec: ExperimentSpec
    game_id: UUID4


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

            experiment = ExperimentMetadata(
                expert=expert, defuser=defuser, room=room, spec=spec, game_id=uuid.uuid4()
            )
            _logger.info(f"Setting-up game[{experiment.game_id}]")
            self.tasks.append(
                asyncio.create_task(coro=self._start_experiment(experiment=experiment))
            )

    @logfire.instrument("Start experiment")
    async def _start_experiment(  # noqa: WPS217
        self, experiment: ExperimentMetadata
    ) -> None:
        """Performs the starting logic for an experiment, then switches to seq/par impl."""
        # Configure the experiment
        await until(get_value=lambda: experiment.room.state, target=RoomStage.ready_for_config)
        _logger.info(f"Starting game[{experiment.game_id}]")
        _ = await asyncio.gather(
            experiment.room.client.configure_experiment(config=experiment.spec.mission_spec),
            experiment.expert.client.start_experiment(
                game_metadata=GameMetadata(
                    experiment_spec=experiment.spec,
                    player_metadata=experiment.expert.metadata,
                    game_id=experiment.game_id,
                )
            ),
            experiment.defuser.client.start_experiment(
                game_metadata=GameMetadata(
                    experiment_spec=experiment.spec,
                    player_metadata=experiment.defuser.metadata,
                    game_id=experiment.game_id,
                )
            ),
        )

        # Start game and switch to correct communication style
        await until(get_value=lambda: experiment.room.state, target=RoomStage.ready_for_start)
        _ = await experiment.room.client.start_experiment()

        match experiment.spec.communication_style:
            case "parallel":
                await self._parallel_experiment(experiment=experiment)

            case "sequential":
                await self._sequential_experiment(experiment=experiment)

    @logfire.instrument("Run parallel experiment")
    async def _parallel_experiment(self, experiment: ExperimentMetadata) -> None:
        """Runs an experiment where both players can act at the same time."""
        _logger.info("Starting parallel experiment")
        _ = await asyncio.gather(
            experiment.expert.client.run_for_game(), experiment.defuser.client.run_for_game()
        )

        _logger.info(f"Running game[{experiment.game_id}]")
        while experiment.room.state is not RoomStage.done:
            if (
                (not experiment.room.is_running)
                or (not experiment.expert.is_running)
                or (not experiment.defuser.is_running)
            ):
                # If the experiment fails, it needs to run again, but we still want metrics
                _logger.error("Something died, stopping experiment and returning to the pool")
                self.experiments.add(experiment.spec)
                break

            await asyncio.sleep(1)

        await self._end_experiment(experiment=experiment)

    @logfire.instrument("Run Sequential experiment")
    async def _sequential_experiment(self, experiment: ExperimentMetadata) -> None:
        """Runs an experiment where players take turns."""
        _logger.info("Starting sequential experiment")
        _logger.info(f"Running game[{experiment.game_id}]")

        while experiment.room.state is not RoomStage.done:
            _ = await experiment.expert.client.run_for_turn()
            _ = await experiment.defuser.client.run_for_turn()

            # BUG: This does not run often enough
            if (
                (not experiment.room.is_running)
                or (not experiment.expert.is_running)
                or (not experiment.defuser.is_running)
            ):
                # If the experiment fails, it needs to run again, but we still want metrics
                _logger.error("Something died, stopping experiment and returning to the pool")
                self.experiments.add(experiment.spec)
                break

            await asyncio.sleep(1)

        await self._end_experiment(experiment=experiment)

    @logfire.instrument("End experiment")
    async def _end_experiment(self, experiment: ExperimentMetadata) -> None:
        """Performs the finishing logic for an experiment."""
        _logger.info(f"Finishing game[{experiment.game_id}]")
        _ = await experiment.room.client.reset_room()
        _ = await asyncio.gather(
            experiment.expert.client.stop_experiment(), experiment.defuser.client.stop_experiment()
        )

        experiment.expert.in_experiment = False
        experiment.defuser.in_experiment = False
        experiment.room.in_experiment = False
