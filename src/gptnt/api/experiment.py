import asyncio
import uuid

import logfire
from pydantic import UUID4
from structlog import get_logger

from gptnt.api.player_client import SupervisedPlayerClient
from gptnt.api.room_client import SupervisedRoomManagerClient
from gptnt.api.structures import GameMetadata, RoomStage
from gptnt.common.async_ops import healthcheck_interval, until
from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.ktane.experiments.experiments import ExperimentSpec
from gptnt.players.ai.prompts import send_reflection_message
from gptnt.players.structures import NO_NEW_MESSAGES_SENTINEL

_logger = get_logger()


def were_last_n_messages_empty(
    *,
    raw_ds_messages: list[str],
    num_to_check: int = 5,
    no_new_message_sentinel: str = NO_NEW_MESSAGES_SENTINEL,
) -> bool:
    """Detect if the last n messages were just `"do nothing".

    Because messages can go on for a while, we use some iterators for this.
    """
    # Get the last n messages from the dialogue space
    message_keys_to_check = raw_ds_messages[-num_to_check:]
    return all(message == no_new_message_sentinel for message in message_keys_to_check)


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
    sequential_fail_count_threshold: int = 3
    """Number of times the endpoint can fail in a row before stopping the experiment."""

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

        # Create a watcher for the dialogue space
        self._dialogue_watcher = DialogueSpaceClient.from_url(
            self._room.metadata.dialogue_space_url
        )

        # Lifecycle
        self.lifecycle_task = asyncio.create_task(coro=self.lifecycle_loop())
        self.supervisor_task = asyncio.create_task(coro=self.supervisor_loop())

    async def lifecycle_loop(self) -> None:  # noqa: WPS217 (This is a lifecycle, the whole point is awaiting lots of stuff)
        """Runs the experiment."""
        with logfire.span("Prepare experiment"):
            # 1. Configure the experiment
            await until(get_value=lambda: self._room.state, target=RoomStage.ready_for_config)
            # TODO: Do something when we can't configure the experiment
            is_configured = await self._room.client.configure_experiment(self.spec.mission_spec)

            if not is_configured:
                _logger.exception("Failed to configure experiment. Bailing out")
                await self.stop_lifecycle()
                return

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

        # TODO: Connect the dialogue watcher

        # 4. Run correct experiment
        match self.spec.communication_style:
            case "parallel":
                await self._run_parallel()
            case "sequential":
                await self._run_sequential()

        # 5. Stop experiment
        self.completed_successfully = True
        await send_reflection_message(
            ktane_url=self._room.metadata.ktane_url,
            dialogue_space_url=self._room.metadata.dialogue_space_url,
        )
        with logfire.span("Stop successful experiment"):
            await self.stop_lifecycle()

    @logfire.instrument("Stop experiment lifecycle")
    async def stop_lifecycle(self, *, is_broken: bool = False) -> None:
        """Stops the current experiment.

        Either because the mission is over or an error occurred.
        """
        _logger.info(f"Finishing game [{self._uuid}]")

        with logfire.span("Stop expert"):
            _ = await self._expert.client.stop_experiment(has_crashed=is_broken)
            self._expert.in_experiment = False

        with logfire.span("Stop defuser"):
            _ = await self._defuser.client.stop_experiment(has_crashed=is_broken)
            self._defuser.in_experiment = False

        # Reset the room
        with logfire.span("Reset room"):
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
            is_invalid_room_state = (
                self._is_started_room_in_bad_state or self._is_configured_room_in_bad_state
            )
            if is_invalid_room_state:
                _logger.info(f"Wrong state entered: {self._room.state}")

            player_or_room_died: bool = (
                (not self._expert.is_running)
                or (not self._defuser.is_running)
                or (not self._room.is_running)
            )

            # Something went wrong, stop this experiment
            if is_invalid_room_state or player_or_room_died:
                with logfire.span("Stop broken experiment"):
                    await self.stop_lifecycle(is_broken=True)

            await healthcheck_interval()

    @logfire.instrument("Run Experiment (Sequential)")
    async def _run_sequential(self) -> None:
        """Runs the experiment in sequential mode."""
        defuser_sequential_fail_count = 0
        expert_sequential_fail_count = 0
        while self._room.state is not RoomStage.done:
            with logfire.span("Defuser turn"):
                is_success = await self._defuser.client.run_for_turn()
                if not is_success:
                    defuser_sequential_fail_count += 1

                if defuser_sequential_fail_count > self.sequential_fail_count_threshold:
                    _logger.error("Defuser failed too many times in a row. Stopping experiment")
                    await self.stop_lifecycle(is_broken=True)

            with logfire.span("Expert turn"):
                is_success = await self._expert.client.run_for_turn()
                if not is_success:
                    expert_sequential_fail_count += 1
                if expert_sequential_fail_count > self.sequential_fail_count_threshold:
                    _logger.error("Expert failed too many times in a row. Stopping experiment")
                    await self.stop_lifecycle(is_broken=True)

    @logfire.instrument("Run Experiment (Parallel)")
    async def _run_parallel(self) -> None:
        """Runs the experiment in parallel mode."""
        _ = await asyncio.gather(
            self._expert.client.run_for_game(), self._defuser.client.run_for_game()
        )
        await until(get_value=lambda: self._room.state, target=RoomStage.done)

    @property
    def _is_started_room_in_bad_state(self) -> bool:
        """Returns True if the room is in a bad state."""
        return self._room.state not in [
            RoomStage.ready_for_start,
            RoomStage.in_experiment,
            RoomStage.done,
        ]

    @property
    def _is_configured_room_in_bad_state(self) -> bool:
        """Returns True if the room is in a bad state."""
        return self._room.state not in [
            RoomStage.ready_for_config,
            RoomStage.ready_for_start,
            RoomStage.in_experiment,
            RoomStage.done,
        ]

    @property
    async def _consecutive_do_nothing_over_threshold(self) -> bool:
        """Returns True if the agents have sent too many do nothing messages in a row."""
        # Pull messages with the watcher client
        _ = await self._dialogue_watcher.pull_messages()

        is_too_many_do_nothings = were_last_n_messages_empty(
            raw_ds_messages=self._dialogue_watcher.messages_pulled, num_to_check=5
        )
        return is_too_many_do_nothings
