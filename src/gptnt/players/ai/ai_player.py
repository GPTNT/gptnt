import abc
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, override

import structlog
from pydantic_ai import Agent, BinaryContent, UsageLimitExceeded
from pydantic_ai.usage import Usage, UsageLimits

from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.players.actions import DoNothingAction, SendMessageAction
from gptnt.players.base_player import BasePlayer, UnhealthyPlayerError

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage

log = structlog.get_logger()


class AIPlayer[AgentDepsT, ResultDataT](BasePlayer, abc.ABC):
    """Base generic class for AI actors/agents that play the game.

    This class brings together all the other clients that are needed for this actor to have a role
    in the game, allow them to directly communicate with their dependencies to make decisions and
    take actions.

    Notes:
        This class is an abstract class that is also a generic. Therefore the implementing class must provide the type of the data that the agent will return.
    """

    def __init__(
        self,
        agent: Agent[AgentDepsT, ResultDataT],
        dialogue_space_client: DialogueSpaceClient,
        *,
        agent_usage_limits: UsageLimits | None = None,
        no_new_messages_sentinel_token: str = "<no_new_messages>",  # noqa: S107
    ) -> None:
        self.agent = agent
        self.dialogue_space_client = dialogue_space_client

        self.usage = Usage()
        self.usage_limits = agent_usage_limits or UsageLimits()

        # PAI expects either messages or None, so we can just init with None
        self._message_history: list[ModelMessage] | None = None

        self._no_new_messages_sentinel_token = no_new_messages_sentinel_token

    @abc.abstractmethod
    def agent_result_type_to_function(
        self, result_type: type[ResultDataT]
    ) -> Callable[[ResultDataT], Awaitable[None]]:
        """Map the result type from the AI model to a method within the function.

        This will allow us to dynamically convert the result from the AI model to a function that
        can be called to carry the logic forwards.
        """
        raise NotImplementedError

    @override
    async def run(self) -> None:
        """Run the decision making process for the player.

        This will continually run forever/until we stop it.
        """
        raise NotImplementedError

    async def run_once(self) -> None:
        """Run the decision making process for the player once."""
        await self.health_check()

        agent_output = await self.send_request_to_agent()
        _ = await self.direct_output_from_agent(agent_output)

    @override
    async def connect(self) -> None:
        _ = await self.dialogue_space_client.connect()

        log.debug("Connected to all clients.")

    @override
    async def health_check(self) -> None:
        try:  # noqa: WPS229 -- these raise the same error
            self.usage_limits.check_before_request(self.usage)
            self.usage_limits.check_tokens(self.usage)
        except UsageLimitExceeded as err:
            raise UnhealthyPlayerError("Usage limit exceeded") from err

        if not self.dialogue_space_client.is_connected:
            raise UnhealthyPlayerError("Dialogue space client is not connected.")

        log.debug("Health check passed.")

    async def send_message_to_dialogue_space(self, message: SendMessageAction) -> None:
        """Send a message to the dialogue space for the current agent."""
        return await self.dialogue_space_client.send_message(message.message)

    async def pull_unread_messages_from_dialogue_space(self) -> str:
        """Pull messages from the dialogue space."""
        messages = await self.dialogue_space_client.pull_messages()
        log.debug(f"Pulled {len(messages)} messages from dialogue space.")

        if not messages:
            return self._no_new_messages_sentinel_token

        # Flatten the messages into a single string
        return "\n".join(messages)

    @abc.abstractmethod
    async def build_agent_input(self) -> str | list[str | BinaryContent]:
        """Build the input for the agent."""
        raise NotImplementedError

    async def direct_output_from_agent(self, agent_output: ResultDataT) -> None:
        """Process output from Agent and direct to correct function.

        Once it comes in, index the type in the agent_result_type_to_function and call the function
        that is mapped to that type. This will allow us to dynamically convert the result from the
        AI model to a function that can be called to carry the logic forwards.
        """
        method = self.agent_result_type_to_function(type(agent_output))
        return await method(agent_output)

    async def do_nothing_action(self, _: DoNothingAction) -> None:
        """Do nothing action."""
        log.debug("Doing nothing.")

    async def send_request_to_agent(self) -> ResultDataT:
        """Send the content to the agent and get it to make a decision and perform an action.

        Raises:
            `pydantic_ai.exceptions.UsageLimitExceeded`: If next request would exceed the usage
            limit.
        """
        message_input = await self.build_agent_input()
        request_deps = self.build_deps_for_request()
        agent_output = await self.agent.run(
            message_input,
            deps=request_deps,
            usage=self.usage,
            message_history=self._message_history,
        )

        # Updage usage after the request
        self.usage = agent_output.usage()
        # Update the message history
        self._message_history = agent_output.all_messages()

        # Return the actual data
        return agent_output.data

    @abc.abstractmethod
    def build_deps_for_request(self) -> AgentDepsT:
        """Build the dependencies for the agent request."""
        raise NotImplementedError

    def reset_message_history(self) -> None:
        """Explicitly reset the message history.

        Useful when we want to clear the dialogue history and start fresh, such as when the context
        length gets too long.
        """
        self._message_history = None
