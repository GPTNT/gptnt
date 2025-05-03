from typing import TYPE_CHECKING

import logfire
from structlog import get_logger

from gptnt.api.experiment import Experiment
from gptnt.api.player_client import SupervisedPlayerClient
from gptnt.api.room_client import SupervisedRoomManagerClient
from gptnt.api.structures import RoomStage
from gptnt.api.tinder import get_playable_pairings
from gptnt.common.async_ops import busy_wait_interval

if TYPE_CHECKING:
    import asyncio

    from gptnt.ktane.experiments.experiments import ExperimentSpec

_logger = get_logger()


connected_rooms_gauge = logfire.metric_gauge(
    "connected_rooms", description="Number of connected rooms"
)
available_rooms_gauge = logfire.metric_gauge(
    "available_rooms", description="Number of available rooms"
)
connected_players_gauge = logfire.metric_gauge(
    "connected_players", description="Number of connected players"
)
available_players_gauge = logfire.metric_gauge(
    "available_players", description="Number of available players"
)


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
        self.running_experiments: set[Experiment] = set()

        # Connection Tracking
        self.players: list[SupervisedPlayerClient] = []
        self.rooms: list[SupervisedRoomManagerClient] = []

    def get_available_rooms(self) -> list[SupervisedRoomManagerClient]:
        """Returns a list of all available rooms."""
        available_rooms = [
            room
            for room in self.rooms
            # Ensure room is running and not in an experiment
            if room.is_running
            and not room.in_experiment
            # And also ensure the room is waiting for a config
            and room.state is RoomStage.ready_for_config
        ]
        connected_rooms_gauge.set(len(self.rooms))
        available_rooms_gauge.set(len(available_rooms))
        return available_rooms

    def get_available_players(self) -> set[SupervisedPlayerClient]:
        """Returns a list of all available players."""
        available_players = {
            player
            for player in self.players
            # Ensure player is running and not in an experiment
            if player.is_running and not player.in_experiment
        }
        connected_players_gauge.set(len(self.players))
        available_players_gauge.set(len(available_players))
        return available_players

    # Experiment logic
    async def main_loop(self) -> None:
        """Runs the main logic for the Experiment Manager.

        Culls dead connections and supervisors. Starts new experiments when valid pairings are
        found. BUG: Dead connections not culled.
        """
        while not self.should_exit:
            # Start experiments that have valid pairings available
            await self.start_available_experiments()

            # Clear any dead client supervisors
            self.tasks = [task for task in self.tasks if not task.done()]

            # Clear any dead experiments and add failed specs back into the pool
            for experiment in self.running_experiments:
                if experiment.lifecycle_task.done() and not experiment.completed_successfully:
                    _logger.warning("Experiment ended early, re-adding to todo pool")
                    self.experiments.add(experiment.spec)
            self.running_experiments = {
                running_experiment
                for running_experiment in self.running_experiments
                if not running_experiment.lifecycle_task.done()
            }

            # Short delay to let the system breathe
            await busy_wait_interval()

    async def start_available_experiments(self) -> None:
        """Starts all ExperimentConfig's that have the correct players and rooms available."""
        available_rooms = self.get_available_rooms()
        available_players = self.get_available_players()

        _logger.debug(
            f"Available rooms: {len(available_rooms)}, available players: {len(available_players)}"
        )

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

            self.experiments.remove(spec)

            with logfire.span(f"Experiment ({spec.experiment_name})", experiment=spec):
                self.running_experiments.add(
                    Experiment(expert=expert, defuser=defuser, room=room, spec=spec)
                )
