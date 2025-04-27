import abc
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import override

import logfire
import structlog
from pydantic_ai import Agent, BinaryContent, UsageLimitExceeded
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import Usage, UsageLimits

from gptnt.common.instrumentation import InstrumentationDataclassMixin
from gptnt.players.actions import DoNothingAction, SendMessageAction
from gptnt.players.base_player import BasePlayer
from gptnt.players.structures import UnhealthyPlayerError

log = structlog.get_logger()


@dataclass(kw_only=True)
class AIPlayer[AgentDepsT, OutputDataT](BasePlayer, InstrumentationDataclassMixin, abc.ABC):
    """Base generic class for AI actors/agents that play the game.

    This class brings together all the other clients that are needed for this actor to have a role
    in the game, allow them to directly communicate with their dependencies to make decisions and
    take actions.

    Notes:
        This class is an abstract class that is also a generic. Therefore the implementing class must provide the type of the data that the agent will return.
    """

    agent: Agent[AgentDepsT, OutputDataT]
    agent_usage_limits: UsageLimits | None = None

    usage: Usage = field(default_factory=Usage)
    usage_limits: UsageLimits = field(default_factory=UsageLimits)

    # # PAI expects either messages or None, so we can just init with None
    _message_history: list[ModelMessage] = field(default_factory=list)

    _no_new_messages_sentinel_token: str = field(default="<no_new_messages>")

    @override
    def perform_instrumentation(self) -> None:
        log.debug("Instrumenting AI player.")
        # this is noqa'd since the generic types are not lining up within the instrument. That is
        # annoying but it's fine.
        logfire.instrument_pydantic_ai(self.agent)  # pyright: ignore[reportArgumentType, reportCallIssue]

    @abc.abstractmethod
    def agent_output_type_to_function(
        self, output_type: type[OutputDataT]
    ) -> Callable[[OutputDataT], Awaitable[None]]:
        """Map the output type from the AI model to a method within the function.

        This will allow us to dynamically convert the output from the AI model to a function that
        can be called to carry the logic forwards.
        """
        raise NotImplementedError

    @override
    async def on_startup(self) -> None:
        return  # noqa: WPS324

    @override
    async def run(self) -> None:
        """Run the decision making process for the player.

        This will continually run forever/until we stop it.
        """
        with logfire.span(
            f"Run AI Player ({self.metadata.player_type}/{self.metadata.player_role})",
            tags=[self.metadata.player_role, self.metadata.player_type],
        ):
            # TODO: I think this is breaking when an action is performed while the lights are off?

            # TODO: This seems like a bad idea? Do we need to fix this
            while True:  # noqa: WPS457
                _ = await self.run_once()
                _ = await asyncio.sleep(1)

    @override
    @logfire.instrument("Run AI player once")
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

    @logfire.instrument("Send message to dialogue space")
    async def send_message_to_dialogue_space(self, message: SendMessageAction) -> None:
        """Send a message to the dialogue space for the current agent."""
        self.tracker.add_message(message=message, role=self.metadata.player_role)
        return await self.dialogue_space_client.send_message(message.message)

    @logfire.instrument("Pull unread messages from dialogue space")
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

    async def direct_output_from_agent(self, agent_output: OutputDataT) -> None:
        """Process output from Agent and direct to correct function.

        Once it comes in, index the type in the agent_output_type_to_function and call the function
        that is mapped to that type. This will allow us to dynamically convert the result from the
        AI model to a function that can be called to carry the logic forwards.
        """
        method = self.agent_output_type_to_function(type(agent_output))
        return await method(agent_output)

    @logfire.instrument("Do nothing")
    async def do_nothing_action(self, _: DoNothingAction) -> None:
        """Do nothing action."""
        log.debug("Doing nothing.")

    @logfire.instrument("Send request to agent")
    async def send_request_to_agent(self) -> OutputDataT:
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
        return agent_output.output

    @abc.abstractmethod
    def build_deps_for_request(self) -> AgentDepsT:
        """Build the dependencies for the agent request."""
        raise NotImplementedError

    def reset_message_history(self) -> None:
        """Explicitly reset the message history.

        Useful when we want to clear the dialogue history and start fresh, such as when the context
        length gets too long.
        """
        self._message_history = []
