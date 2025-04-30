import asyncio
import uuid

import logfire
from pydantic import UUID4
from structlog import get_logger

from gptnt.api.player_client import SupervisedPlayerClient
from gptnt.api.room_client import SupervisedRoomManagerClient
from gptnt.api.structures import GameMetadata, RoomStage
from gptnt.api.tinder import get_playable_pairings
from gptnt.common.async_ops import busy_wait_interval, healthcheck_interval, until
from gptnt.ktane.experiments.experiments import ExperimentSpec

_logger = get_logger()


class Experiment:
    """Self-contained experiment lifecycle."""

    _expert: SupervisedPlayerClient
    _defuser: SupervisedPlayerClient
    _room: SupervisedRoomManagerClient
    spec: ExperimentSpec

    _uuid: UUID4

    # Lifecycle
    lifecycle_task: asyncio.Task[None]
    supervisor_task: asyncio.Task[None]
    _mission_configured: bool = False
    _mission_started: bool = False
    completed_successfully: bool = False

    def __init__(
        self,
        *,
        expert: SupervisedPlayerClient,
        defuser: SupervisedPlayerClient,
        room: SupervisedRoomManagerClient,
        spec: ExperimentSpec,
    ) -> None:
        self._expert = expert
        self._defuser = defuser
        self._room = room
        self.spec = spec

        # ExperimentManager control flags
        expert.in_experiment = True
        defuser.in_experiment = True
        room.in_experiment = True

        # Persistent UUID for the session/game/experiment/run (whatever you want to call it)
        self._uuid = uuid.uuid4()

        # Lifecycle
        self.lifecycle_task = asyncio.create_task(coro=self.lifecycle_loop())
        self.supervisor_task = asyncio.create_task(coro=self.supervisor_loop())

    @logfire.instrument("Started experiment lifecycle")
    async def lifecycle_loop(self) -> None:  # noqa: WPS217 (This is a lifecycle, the whole point is awaiting lots of stuff)
        """Runs the experiment."""
        with logfire.span("Prepare experiment"):
            # 1. Configure the experiment
            await until(get_value=lambda: self._room.state, target=RoomStage.ready_for_config)
            _ = await self._room.client.configure_experiment(self.spec.mission_spec)
            self._mission_configured = True

            # 2. Connect the players to the room
            _ = await asyncio.gather(  # noqa: WPS476
                self._expert.client.join_room(room=self._room.metadata),
                self._defuser.client.join_room(room=self._room.metadata),
            )

            await until(get_value=lambda: self._room.state, target=RoomStage.ready_for_start)

            # 3. Start the experiment
            _ = await asyncio.gather(
                self._expert.client.start_experiment(
                    game_metadata=GameMetadata(
                        experiment_spec=self.spec,
                        player_metadata=self._expert.metadata,
                        game_id=self._uuid,
                    )
                ),
                self._defuser.client.start_experiment(
                    game_metadata=GameMetadata(
                        experiment_spec=self.spec,
                        player_metadata=self._defuser.metadata,
                        game_id=self._uuid,
                    )
                ),
                self._room.client.start_experiment(),
            )
            self._mission_started = True

        # 4. Run correct experiment
        match self.spec.communication_style:
            case "parallel":
                await self._run_parallel()
            case "sequential":
                await self._run_sequential()

        # 5. Stop experiment
        with logfire.span("Stop Experiment"):
            self.completed_successfully = True
            await self.stop_lifecycle()

    @logfire.instrument("Stopped experiment lifecycle")
    async def stop_lifecycle(self) -> None:
        """Stops the current experiment.

        Either because the mission is over or an error occurred.
        """
        _logger.info(f"Finishing game [{self._uuid}]")
        to_reset = [
            player.client.stop_experiment()
            for player in (self._expert, self._defuser)
            if player.is_running
        ]
        _ = await asyncio.gather(*to_reset, return_exceptions=True)
        self._expert.in_experiment = False
        self._defuser.in_experiment = False

        # Reset the room
        _logger.debug("Resetting room")
        # If the room/client is closed for some reasn, don't try to reset it since it will raise a
        # runtime error which is annoying
        if not self._room.is_closed:
            _ = await self._room.client.reset_room()
        self._room.in_experiment = False

        # Stop
        _logger.debug("Stopping tasks")
        _ = self.lifecycle_task.cancel()
        _ = self.supervisor_task.cancel()

    async def supervisor_loop(self) -> None:
        """Runs the experiment supervisor."""
        while not self.completed_successfully:
            # Stop the experiment if there are any problems
            in_invalid_state: bool = (
                self._mission_started
                and self._room.state
                not in [RoomStage.ready_for_start, RoomStage.in_experiment, RoomStage.done]
            ) or (
                self._mission_configured
                and self._room.state
                not in [
                    RoomStage.ready_for_config,
                    RoomStage.ready_for_start,
                    RoomStage.in_experiment,
                ]
            )
            if in_invalid_state:
                _logger.info(f"Wrong state entered: {self._room.state}")

            player_or_room_died: bool = (
                (not self._expert.is_running)
                or (not self._defuser.is_running)
                or (not self._room.is_running)
            )

            if in_invalid_state or player_or_room_died:
                # Something went wrong, stop this experiment
                await self.stop_lifecycle()

            await healthcheck_interval()

    @logfire.instrument("Run Experiment (Sequential)")
    async def _run_sequential(self) -> None:
        """Runs the experiment in sequential mode."""
        while self._room.state is not RoomStage.done:
            with logfire.span("Expert turn"):
                _ = await self._expert.client.run_for_turn()
            with logfire.span("Defuser turn"):
                _ = await self._defuser.client.run_for_turn()

    @logfire.instrument("Run Experiment (Parallel)")
    async def _run_parallel(self) -> None:
        """Runs the experiment in parallel mode."""
        _ = await asyncio.gather(
            self._expert.client.run_for_game(), self._defuser.client.run_for_game()
        )
        await until(get_value=lambda: self._room.state, target=RoomStage.done)


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

            with logfire.span("Experiment"):
                self.running_experiments.add(
                    Experiment(expert=expert, defuser=defuser, room=room, spec=spec)
                )
