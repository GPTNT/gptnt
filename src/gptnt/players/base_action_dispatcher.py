import abc
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import logfire
import structlog

from gptnt.ktane.actions import (
    GameActionTypeWithExtras,
    KtaneBaseAction,
    KtaneGameplayInput,
    RelativeCoordinate,
)
from gptnt.players.actions import (
    DoNothingAction,
    GameInteractionActionType,
    InteractGameAction,
    LotteryGameAction,
    MagicGameAction,
    PlayerOutputType,
    SendMessageAction,
)
from gptnt.players.exceptions import AIResponseErrorType
from gptnt.players.observation_handler import ObservationHandler
from gptnt.players.result import AgentCallResult, DispatchedAgentCallResult
from gptnt.players.specification import PlayerProtocol
from gptnt.processors.image_resizer import CoordinateOutOfBoundsError
from gptnt.processors.set_of_marks import InvalidMarkLocationError

logger = structlog.get_logger()


type DispatchedAgentCall = (
    DispatchedAgentCallResult[SendMessageAction]
    | DispatchedAgentCallResult[DoNothingAction]
    | DispatchedAgentCallResult[KtaneGameplayInput]
)
"""Type alias for the dispatched agent call result.

These are the only things which a dispatched agent call result can be.
"""

type _ActionHandlerType = Callable[..., Awaitable[DispatchedAgentCall]]


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
    ) -> DispatchedAgentCall:
        """Process output from Agent and direct to correct function.

        Once it comes in, index the type in the agent_output_type_to_function and call the function
        that is mapped to that type. This will allow us to convert the result from the AI model to
        a function that can be called to continue the work.
        """
        method = self.agent_output_type_to_function(type(agent_output.output))
        return await method(agent_output)

    def agent_output_type_to_function(
        self, output_type: type[PlayerOutputType]
    ) -> _ActionHandlerType:
        """Map the output type from the AI model to a method within the function.

        This will allow us to convert the output from the AI model to a function that can be called
        to perform the action.
        """
        switcher: dict[type[PlayerOutputType], _ActionHandlerType] = {
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
    ) -> DispatchedAgentCallResult[DoNothingAction]:
        """Do nothing action."""
        return DispatchedAgentCallResult.from_agent_call(action)

    @logfire.instrument("Send game action")
    async def _send_game_action(
        self, action: AgentCallResult[GameInteractionActionType]
    ) -> (
        DispatchedAgentCallResult[DoNothingAction] | DispatchedAgentCallResult[KtaneGameplayInput]
    ):
        """Send a game action to the game.

        One of two things will happen: either it will be converted to a game action and sent to the
        game, or it will be treated as a do nothing action if the conversion for SoM fails.
        """
        try:
            game_action = self.observation_handler.convert_to_game_action(action=action.output)
        except InvalidMarkLocationError:
            logger.warning(
                "Invalid mark location in action, defaulting to DoNothing", action=action
            )
            return await self._do_nothing_action(
                AgentCallResult(
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
                AgentCallResult(
                    output=DoNothingAction(),
                    thoughts=None,
                    usage=action.usage,
                    new_messages=action.new_messages,
                    raw_output=action.raw_output,
                    ai_response_error=[AIResponseErrorType.out_of_bounds_coordinate],
                )
            )

        dispatched_result = DispatchedAgentCallResult[KtaneGameplayInput].from_agent_call(
            AgentCallResult(
                output=game_action,
                thoughts=action.thoughts,
                usage=action.usage,
                new_messages=action.new_messages,
                raw_output=action.raw_output,
                ai_response_error=[],
            )
        )
        _ = await self.send_game_action(action=game_action)
        return dispatched_result

    @logfire.instrument("Send message")
    async def _send_message(
        self, action: AgentCallResult[SendMessageAction]
    ) -> DispatchedAgentCallResult[SendMessageAction]:
        """Send a message to the dialogue space."""
        dispatched_result = DispatchedAgentCallResult[SendMessageAction].from_agent_call(action)
        _ = await self.send_dialogue_message(action.output.message)
        return dispatched_result
