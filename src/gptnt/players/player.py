import abc
from collections.abc import Awaitable, Callable

import structlog
from pydantic_ai import Agent
from pydantic_ai.usage import Usage, UsageLimits

from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.players.actions import DoNothingAction, SendMessageAction

log = structlog.get_logger()


class Player[AgentDepsT, ResultDataT](abc.ABC):
    """Base generic class for all actors/agents that play the game.

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
    ) -> None:
        self.agent = agent
        self.dialogue_space_client = dialogue_space_client

        self.usage = Usage()
        self.usage_limits = agent_usage_limits or UsageLimits()

    @abc.abstractmethod
    def agent_result_type_to_function(
        self, result_type: type[ResultDataT]
    ) -> Callable[[ResultDataT], Awaitable[None]]:
        """Map the result type from the AI model to a method within the function.

        This will allow us to dynamically convert the result from the AI model to a function that
        can be called to carry the logic forwards.
        """
        raise NotImplementedError

    async def run_once(self) -> None:
        """Run the decision making process for the player once."""
        await self.health_check()

        agent_output = await self.send_request_to_agent()
        _ = await self.direct_output_from_agent(agent_output)

    async def connect(self) -> None:
        """Connect the player to all the various clients/connections."""
        _ = await self.dialogue_space_client.connect()

    async def health_check(self) -> None:
        """Check health of all relevant connections, raising exceptions if not healthy.

        Raises:
            `pydantic_ai.exceptions.UsageLimitExceeded`: If next request would exceed the usage
            limit.
        """
        self.usage_limits.check_before_request(self.usage)
        self.usage_limits.check_tokens(self.usage)
        assert self.dialogue_space_client.is_connected

    async def send_message_to_dialogue_space(self, message: SendMessageAction) -> None:
        """Send a message to the dialogue space for the current agent."""
        return await self.dialogue_space_client.send_message(message.message)

    async def pull_unread_messages_from_dialogue_space(self) -> str:
        """Pull messages from the dialogue space."""
        messages = await self.dialogue_space_client.pull_messages()

        # TODO: when there are no messages, the input to the model should be empty?
        if not messages:
            raise ValueError("No messages to pull from the dialogue space.")

        # Flatten the messages into a single string
        return "\n".join(messages)

    @abc.abstractmethod
    async def build_agent_input(self) -> str:
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
        agent_output = await self.agent.run(message_input, deps=request_deps, usage=self.usage)

        # Updage usage after the request
        self.usage = agent_output.usage()

        # Return the actual data
        return agent_output.data

    @abc.abstractmethod
    def build_deps_for_request(self) -> AgentDepsT:
        """Build the dependencies for the agent request."""
        raise NotImplementedError
