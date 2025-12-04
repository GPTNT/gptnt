import abc
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import logfire
import structlog

from gptnt.ktane.actions import GameActionTypeWithMagic, KtaneBaseAction, RelativeCoordinate
from gptnt.players.actions import (
    DoNothingAction,
    GameInteractionActionType,
    InteractGameAction,
    MagicGameAction,
    PlayerOutputType,
    SendMessageAction,
)
from gptnt.players.metrics.episode_tracker import EpisodeTracker
from gptnt.players.observation_handler import ObservationHandler
from gptnt.players.specification import PlayerProtocol
from gptnt.processors.set_of_marks import InvalidMarkLocationError

logger = structlog.get_logger()


@dataclass(kw_only=True)
class BaseActionDispatcher(abc.ABC):
    """Dispatch actions from the agent to where they need to go."""

    tracker: EpisodeTracker
    observation_handler: ObservationHandler

    protocol: PlayerProtocol = field(init=False, repr=False)

    def configure_for_experiment(self, *, protocol: PlayerProtocol, **kwargs: Any) -> None:  # noqa: ARG002
        """Configure the action dispatcher for the experiment."""
        self.protocol = protocol

    async def direct_output_from_agent(self, agent_output: PlayerOutputType) -> None:
        """Process output from Agent and direct to correct function.

        Once it comes in, index the type in the agent_output_type_to_function and call the function
        that is mapped to that type. This will allow us to dynamically convert the result from the
        AI model to a function that can be called to carry the logic forwards.
        """
        method = self.agent_output_type_to_function(type(agent_output))
        return await method(agent_output)

    def agent_output_type_to_function(
        self, output_type: type[PlayerOutputType]
    ) -> Callable[[PlayerOutputType], Awaitable[None]]:
        """Map the output type from the AI model to a method within the function.

        This will allow us to dynamically convert the output from the AI model to a function that
        can be called to carry the logic forwards.
        """
        switcher: dict[type[PlayerOutputType], Callable[..., Awaitable[None]]] = {
            SendMessageAction: self._send_message,
            DoNothingAction: self._do_nothing_action,
            InteractGameAction: self._send_game_action,
            MagicGameAction: self._send_game_action,
        }
        output_handler = next(
            switcher[output_class]
            for output_class in output_type.__mro__
            if output_class in switcher
        )
        if not output_handler:  # pyright: ignore[reportUnnecessaryComparison]
            raise ValueError(
                f"Output type '{output_type}' not found in switcher. Please add it to the switcher."
            )
        return output_handler

    @abc.abstractmethod
    async def send_dialogue_message(self, message: str) -> None:
        """Send the dialogue message to the other player(s)."""
        raise NotImplementedError

    @abc.abstractmethod
    async def send_game_action(
        self, action: KtaneBaseAction[GameActionTypeWithMagic, RelativeCoordinate]
    ) -> None:
        """Send a game action to the current game."""
        raise NotImplementedError

    @logfire.instrument("Do nothing action")
    async def _do_nothing_action(self, action: DoNothingAction) -> None:
        """Do nothing action."""
        self.tracker.add_do_nothing(action, role=self.protocol.role)

    @logfire.instrument("Send game action")
    async def _send_game_action(self, action: GameInteractionActionType) -> None:
        """Send a game action to the game."""
        try:
            game_action = self.observation_handler.convert_to_game_action(action=action)
        except InvalidMarkLocationError:
            logger.warning(
                "Invalid mark location in action, defaulting to DoNothing", action=action
            )
            self.tracker.num_invalid_locations += 1
            return await self._do_nothing_action(action=DoNothingAction())

        self.tracker.add_action(action=action)
        return await self.send_game_action(action=game_action)

    @logfire.instrument("Send message")
    async def _send_message(self, action: SendMessageAction) -> None:
        """Send a message to the dialogue space."""
        self.tracker.add_message(message=action, role=self.protocol.role)
        return await self.send_dialogue_message(action.message)
