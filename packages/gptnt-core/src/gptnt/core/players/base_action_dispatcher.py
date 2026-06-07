import abc
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import logfire
import structlog

from gptnt.core.ktane.actions import (
    GameActionTypeWithExtras,
    KtaneBaseAction,
    KtaneGameplayInput,
    RelativeCoordinate,
)
from gptnt.core.players.actions import (
    DoNothingAction,
    GameInteractionActionType,
    InteractGameAction,
    LotteryGameAction,
    MagicGameAction,
    PlayerOutputType,
    SendMessageAction,
)
from gptnt.core.players.exceptions import AIResponseErrorType
from gptnt.core.players.observation_handler import ObservationHandler
from gptnt.core.players.result import AgentCallResult
from gptnt.core.processors.image_resizer import CoordinateOutOfBoundsError
from gptnt.core.processors.set_of_marks import InvalidMarkLocationError
from gptnt.core.specification import PlayerProtocol

logger = structlog.get_logger()

ActionHandlerType = Callable[
    [AgentCallResult[PlayerOutputType | KtaneGameplayInput]],
    Awaitable[AgentCallResult[PlayerOutputType | KtaneGameplayInput]],
]


@dataclass(kw_only=True)
class BaseActionDispatcher(abc.ABC):
    """Dispatch actions from the agent to where they need to go."""

    observation_handler: ObservationHandler

    protocol: PlayerProtocol = field(init=False, repr=False)

    def configure_for_experiment(self, *, protocol: PlayerProtocol, **kwargs: Any) -> None:  # noqa: ARG002
        """Configure the action dispatcher for the experiment."""
        self.protocol = protocol

    async def direct_output_from_agent(
        self, agent_output: AgentCallResult[PlayerOutputType]
    ) -> AgentCallResult[PlayerOutputType | KtaneGameplayInput]:
        """Process output from Agent and direct to correct function.

        Once it comes in, index the type in the agent_output_type_to_function and call the function
        that is mapped to that type. This will allow us to dynamically convert the result from the
        AI model to a function that can be called to carry the logic forwards.
        """
        method = self.agent_output_type_to_function(type(agent_output.output))
        return await method(agent_output)

    def agent_output_type_to_function(
        self, output_type: type[PlayerOutputType]
    ) -> ActionHandlerType:
        """Map the output type from the AI model to a method within the function.

        This will allow us to dynamically convert the output from the AI model to a function that
        can be called to carry the logic forwards.
        """
        switcher: dict[
            type[PlayerOutputType],
            Callable[..., Awaitable[AgentCallResult[PlayerOutputType | KtaneGameplayInput]]],
        ] = {
            SendMessageAction: self._send_message,
            DoNothingAction: self._do_nothing_action,
            InteractGameAction: self._send_game_action,
            MagicGameAction: self._send_game_action,
            LotteryGameAction: self._send_game_action,
        }
        try:
            output_handler = next(
                switcher[output_class]
                for output_class in output_type.__mro__
                if output_class in switcher
            )
        except StopIteration as err:
            raise ValueError(
                f"Output type '{output_type}' not found in switcher. Please add it to the switcher."
            ) from err
        return output_handler

    @abc.abstractmethod
    async def send_dialogue_message(self, message: str) -> None:
        """Send the dialogue message to the other player(s)."""
        raise NotImplementedError

    @abc.abstractmethod
    async def send_game_action(
        self, action: KtaneBaseAction[GameActionTypeWithExtras, RelativeCoordinate]
    ) -> None:
        """Send a game action to the current game."""
        raise NotImplementedError

    @logfire.instrument("Do nothing action")
    async def _do_nothing_action(
        self, action: AgentCallResult[DoNothingAction]
    ) -> AgentCallResult[DoNothingAction]:
        """Do nothing action."""
        return action

    @logfire.instrument("Send game action")
    async def _send_game_action(
        self, action: AgentCallResult[GameInteractionActionType]
    ) -> AgentCallResult[PlayerOutputType | KtaneGameplayInput]:
        """Send a game action to the game."""
        try:
            game_action = self.observation_handler.convert_to_game_action(action=action.output)
        except InvalidMarkLocationError:
            logger.warning(
                "Invalid mark location in action, defaulting to DoNothing", action=action
            )
            return await self._do_nothing_action(
                AgentCallResult[DoNothingAction](
                    output=DoNothingAction(),
                    thoughts=None,
                    usage=action.usage,
                    new_messages=action.new_messages,
                    raw_output=action.raw_output,
                    ai_response_error=[AIResponseErrorType.invalid_som_location],
                )
            )
        except CoordinateOutOfBoundsError:
            logger.warning(
                "Out of bounds coordinate in action, defaulting to DoNothing", action=action
            )
            return await self._do_nothing_action(
                AgentCallResult[DoNothingAction](
                    output=DoNothingAction(),
                    thoughts=None,
                    usage=action.usage,
                    new_messages=action.new_messages,
                    raw_output=action.raw_output,
                    ai_response_error=[AIResponseErrorType.out_of_bounds_coordinate],
                )
            )

        _ = await self.send_game_action(action=game_action)
        return AgentCallResult[PlayerOutputType | KtaneGameplayInput](
            output=game_action,
            thoughts=action.thoughts,
            usage=action.usage,
            new_messages=action.new_messages,
            raw_output=action.raw_output,
            ai_response_error=[],
        )

    @logfire.instrument("Send message")
    async def _send_message(
        self, action: AgentCallResult[SendMessageAction]
    ) -> AgentCallResult[SendMessageAction]:
        """Send a message to the dialogue space."""
        _ = await self.send_dialogue_message(action.output.message)
        return action
