from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import cached_property
from types import TracebackType
from typing import override
from uuid import uuid4

import logfire
from pydantic.types import UUID4
from structlog import get_logger

from gptnt.api.base_em_client import BaseEMClient
from gptnt.api.base_rabbitmq_client import ExceptionUnhandledError
from gptnt.api.commands import (
    ConfigurePlayerCommand,
    GameGetObservationCommand,
    PlayerCommand,
    ReflectionCommand,
    RunForwardOnceCommand,
    StopExperimentCommand,
)
from gptnt.api.events import PlayerConnectEvent
from gptnt.api.experiment_manager.experiment_descriptor import ExperimentDescriptor
from gptnt.api.game_manager.game_instance import GameObservationResponse
from gptnt.ktane.actions import KtaneBaseAction, RelativeCoordinate
from gptnt.ktane.state.bomb import BombState
from gptnt.players.spec import NO_NEW_MESSAGES_SENTINEL, PlayerMetadata, PlayerSpec

logger = get_logger()

DEFAULT_TIMEOUT = 600


@dataclass(kw_only=True)
class BasePlayer(BaseEMClient, ABC):
    """Base class for players."""

    metadata: PlayerMetadata
    uuid: UUID4 = field(default_factory=uuid4)

    _current_game_uuid: UUID4 | None = field(default=None, init=False)
    _current_room_uuid: UUID4 | None = field(default=None, init=False)
    _current_spec: PlayerSpec | None = field(default=None, init=False)

    _unpulled_messages: list[str] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        """Logic for pre-startup."""
        super().__post_init__()

        # Add handlers to this players queues
        self.api_queues.player_command(self.uuid).subscribe(self.handle_command)
        self.api_queues.player_messages(self.uuid).subscribe(self.handle_message)
        self.api_queues.player_run(self.uuid).subscribe(self.handle_run)

    @cached_property
    @override
    def connection_message(self) -> PlayerConnectEvent:
        """Specifies the connection message to send to the EM on startup."""
        return PlayerConnectEvent(uuid=self.uuid, metadata=self.metadata)

    @override
    async def handle_background_task_exception(
        self,
        exc_type: type[BaseException] | None = None,
        exc_obj: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        """Handle uncaught exceptions from background_tasks."""
        # TODO: Add any error handling for tasks in self.background_tasks
        raise ExceptionUnhandledError

    async def handle_command(self, command: PlayerCommand) -> None:
        """Handler for commands received from the room service."""
        if isinstance(command, ConfigurePlayerCommand):
            if self._current_game_uuid or self._current_room_uuid:
                logger.warning("Received ConfigurePlayerCommand during an experiment.")
            else:
                self._current_game_uuid = command.game_uuid
                self._current_room_uuid = command.room_uuid
                self._current_spec = command.player_spec
                await self.on_experiment_start(
                    experiment_descriptor=command.experiment_descriptor, spec=command.player_spec
                )

        if isinstance(command, (StopExperimentCommand, ReflectionCommand)):
            if isinstance(command, ReflectionCommand):
                await self.handle_reflection_message(command)
            is_hard_crash = isinstance(command, StopExperimentCommand) and command.hard_crash
            await self.on_experiment_stop(
                is_hard_crash=is_hard_crash, bomb_state=command.bomb_state
            )

            logger.info("Received StopExperimentCommand, stopping experiment.")
            self._current_game_uuid = None
            self._current_room_uuid = None
            await self.ready()

    async def handle_run(self, _: RunForwardOnceCommand) -> None:
        """Runs a single forward pass."""
        await self.forward_pass()
        logger.debug("Forward pass completed")

    @logfire.instrument("Send dialogue message")
    async def send_dialogue_message(self, message: str) -> None:
        """Send a dialogue message to the current game."""
        if not self._current_game_uuid or not self._current_spec:
            logger.warning("Tried to send message out-with a running experiment.")
            return

        await self.api_routes.game_messages(
            self._current_game_uuid, self._current_spec.role
        ).publish(message)
        logger.debug("Sent dialogue message", message=message, from_role=self._current_spec.role)

    @logfire.instrument("Send game action")
    async def send_game_action(self, action: KtaneBaseAction[RelativeCoordinate]) -> None:
        """Send a game action to the current game."""
        if not self._current_game_uuid or not self._current_spec:
            logger.warning("Tried to send game action out-with a running experiment.")
            return

        await self.api_queues.game_actions(self._current_game_uuid).route.publish(action)
        logger.debug("Sent game action", action=action, from_role=self._current_spec.role)

    async def pull_messages(self) -> str:
        """Pull messages from the queue.

        If there are several, we return a join of them. If there are none, we return the default
        sentinel.
        """
        if not self._unpulled_messages:
            logger.debug("No new messages to pull.")
            return NO_NEW_MESSAGES_SENTINEL

        # Flatten the messages into a single string
        new_messages = "\n".join(self._unpulled_messages)
        self._unpulled_messages.clear()
        return new_messages

    @logfire.instrument("Pull observation")
    async def pull_observation(self) -> GameObservationResponse | None:
        """Pull the latest observation from the game."""
        if not self._current_game_uuid:
            logger.warning("Tried to pull observation out-with a running experiment.")
            return None

        try:
            observations = await self.api_queues.game_command(
                self._current_game_uuid
            ).route.publish_with_response(
                GameGetObservationCommand(), fail_after=300, response_type=GameObservationResponse
            )
        except TimeoutError:
            logger.exception("Failed to pull observation, timed out.")
            return None

        logger.debug("Pulled observations.")
        return observations

    @logfire.instrument("Handle message")
    async def handle_message(self, message: str) -> None:
        """Handler for new (dialogue) messages."""
        self._unpulled_messages.append(message)
        logger.debug("Received message", message=message)

    @abstractmethod
    async def on_experiment_start(
        self, *, experiment_descriptor: ExperimentDescriptor, spec: PlayerSpec
    ) -> None:
        """Logic for starting an experiment.

        The experiment spec will be passed in here.
        """
        raise NotImplementedError

    @abstractmethod
    async def on_experiment_stop(
        self, *, is_hard_crash: bool = False, bomb_state: BombState | None = None
    ) -> None:
        """Logic for ending an experiment."""
        raise NotImplementedError

    @abstractmethod
    async def forward_pass(self) -> None:
        """Logic for running a single "turn" in a game.

        Human players can leave this empty.
        """
        raise NotImplementedError

    @abstractmethod
    async def handle_reflection_message(self, reflection_command: ReflectionCommand) -> None:
        """Send the reflection message."""
        raise NotImplementedError
