import abc
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import cast, override

import logfire
import structlog
from pydantic_ai import Agent, BinaryContent, UsageLimitExceeded
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.usage import Usage, UsageLimits

from gptnt.common.async_ops import busy_wait_interval
from gptnt.common.instrumentation import InstrumentationDataclassMixin
from gptnt.ktane.game_settings import KtaneSettings
from gptnt.players.actions import DoNothingAction, SendMessageAction
from gptnt.players.ai.prompts import coerce_reflection_message_output, load_reflection_prompt
from gptnt.players.ai.tokens import estimate_tokens_for_image_per_model
from gptnt.players.ai.usage import PlayerUsage
from gptnt.players.base_player import BasePlayer
from gptnt.players.metrics.structures import AdditionalEndGameMetrics
from gptnt.players.structures import NO_NEW_MESSAGES_SENTINEL, PlayerStage, UnhealthyPlayerError

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

    usage: Usage = field(default_factory=Usage)
    usage_limits: UsageLimits = field(default_factory=UsageLimits)

    player_usage: PlayerUsage = field(init=False)

    should_reflect_on_game_at_end: bool = field(default=False)

    _no_new_messages_sentinel_token: str = field(default=NO_NEW_MESSAGES_SENTINEL)

    @override
    def __post_init__(self) -> None:
        game_settings = KtaneSettings()
        self.player_usage = PlayerUsage(
            model_name=self.model_name,
            role=self.metadata.player_role,
            tokens_per_image=estimate_tokens_for_image_per_model(
                self.model_name, width=game_settings.game_width, height=game_settings.game_height
            ),
        )

        return super().__post_init__()

    @property
    def model_name(self) -> str:
        """Get the name of the model."""
        if isinstance(self.agent.model, str):
            return self.agent.model
        if isinstance(self.agent.model, Model):
            return self.agent.model.model_name
        raise ValueError("Model name not found")

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
    async def on_experiment_stop(
        self, *, additional_end_game_metrics: AdditionalEndGameMetrics | None = None
    ) -> None:
        """Things to do when the experiment stops."""
        if self.should_reflect_on_game_at_end:
            self.metadata.stage = PlayerStage.reflecting
            log.debug("Reflecting on the game at end")
            reflection = await self.handle_reflection_prompt()
            if reflection is not None:
                self.tracker.add_reflection(message=reflection, role=self.metadata.player_role)

        self.metadata.stage = PlayerStage.stopping
        # Update tracker with usage
        self.tracker.num_prompt_truncations = self.player_usage.num_times_truncated
        # Finalize the tracking of usage metrics for the current step
        self._track_step()
        await busy_wait_interval()
        await super().on_experiment_stop(additional_end_game_metrics=additional_end_game_metrics)

    @override
    async def run_parallel(self) -> None:
        """Run the decision making process for the player.

        This will continually run forever/until we stop it.
        """
        with logfire.span(
            f"Run Parallel ({self.metadata.player_type}/{self.metadata.player_role})",
            tags=[self.metadata.player_role, self.metadata.player_type],
            limits=self.usage_limits,
        ):
            # TODO: I think this is breaking when an action is performed while the lights are off?

            # TODO: This seems like a bad idea? Do we need to fix this
            while True:  # noqa: WPS457
                await self.health_check()

                agent_output = await self.send_request_to_agent()
                _ = await self.direct_output_from_agent(agent_output)

                _ = await busy_wait_interval()

    @override
    @logfire.instrument("Run AI player once (sequential decision making)")
    async def run_sequential(self) -> None:
        """Run the decision making process for the player once."""
        await self.health_check()

        agent_output = await self.send_request_to_agent()
        _ = await self.direct_output_from_agent(agent_output)

    @override
    async def connect(self) -> None:
        self.reset_message_history()
        _ = await self.dialogue_space_client.connect()

        log.debug("Connected to all clients.")

    @override
    async def health_check(self) -> None:
        log.debug("Checking usage limits", limits=self.usage_limits, usage=self.usage)
        try:  # noqa: WPS229 -- these raise the same error
            self.usage_limits.check_tokens(self.usage)
        except UsageLimitExceeded as err:
            raise UnhealthyPlayerError("Too many tokens exceeded") from err

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
    async def do_nothing_action(self, do_nothing: DoNothingAction) -> None:
        """Do nothing action."""
        self.tracker.add_do_nothing(action=do_nothing, role=self.metadata.player_role)
        log.debug("Doing nothing.")

    @logfire.instrument("Send request to agent")
    async def send_request_to_agent(self) -> OutputDataT:
        """Send the content to the agent and get it to make a decision and perform an action.

        Raises:
            `pydantic_ai.exceptions.UsageLimitExceeded`: If next request would exceed the usage
            limit.
        """
        # Check if we need to truncate the history
        self.truncate_message_history()

        message_input = await self.build_agent_input()
        request_deps = self.build_deps_for_request()
        try:
            agent_output = await self.agent.run(
                message_input, deps=request_deps, message_history=self.player_usage.to_history()
            )
        except ModelHTTPError as err:
            if "filtered due to the prompt triggering Azure OpenAI's content" in err.message:
                log.exception("Filtered due to content policy", error=err)
                self.tracker.guardrail_violations += 1
            raise

        # Updage usage after the request
        self.player_usage.update(
            new_messages=agent_output.new_messages(), usage=agent_output.usage()
        )
        self._track_step(agent_output.usage())

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
        self.player_usage.reset()
        self.usage = Usage()

    @logfire.instrument("Truncate message history")
    def truncate_message_history(self) -> None:
        """Reduce the context window by removing the oldest messages.

        This is useful when the context length gets too long and we need to reduce it, however we
        need to make sure that we don't remove the manual from the context for the expert.
        """
        if not self.usage_limits.total_tokens_limit:
            log.debug("No usage limit set, not truncating message history.")
            return

        while self.player_usage.should_truncate_message_history(
            model_context_length=self.usage_limits.total_tokens_limit
        ):
            log.info(
                "Truncating message history",
                history_length=len(self.player_usage.to_history()),
                context_length=self.player_usage.context_length,
                num_times_truncated=self.player_usage.num_times_truncated,
            )
            self.player_usage.truncate_history()

    @logfire.instrument("Reflect on the game")
    async def handle_reflection_prompt(self) -> SendMessageAction | None:
        """Send/get the reflection message from the AI given the state."""
        # pull final message from dialogue space
        final_message = await self.pull_unread_messages_from_dialogue_space()

        if final_message == self._no_new_messages_sentinel_token:
            log.exception("No new messages to send to the agent.")
            return None

        # Load the reflection prompt
        reflection_prompt = load_reflection_prompt()

        # Coerce the final response in case it goes wrong
        self.agent.output_validator(coerce_reflection_message_output)  # pyright: ignore[reportCallIssue,reportArgumentType]

        response = await self.agent.run(
            [final_message, reflection_prompt],
            deps=self.build_deps_for_request(),
            message_history=self.player_usage.to_history(),
        )
        # update the usage
        self.usage = response.usage()
        self.player_usage.update(new_messages=response.new_messages(), usage=response.usage())

        # return the response, which is a SendMessageAction (since we are coercing it)
        return cast("SendMessageAction", response.output)

    @property
    def _message_history(self) -> list[ModelMessage]:
        """Get the message history for the player."""
        return self.player_usage.to_history()

    def _track_step(self, agent_output_usage: Usage | None = None) -> None:
        """Track the step for the player."""
        output_data = {
            "step": self.player_usage.num_requests,
            "num_times_truncated": self.player_usage.num_times_truncated,
            "game_cost": self.player_usage.total_cost(),
        }
        if agent_output_usage is not None:
            output_data = {
                **output_data,
                "request_tokens": agent_output_usage.request_tokens,
                "response_tokens": agent_output_usage.response_tokens,
                "total_tokens": agent_output_usage.total_tokens,
                "request_cost": self.player_usage.message_request_tokens_cost(message_idx=-1),
                "response_cost": self.player_usage.message_response_tokens_cost(message_idx=-1),
                "message_cost": self.player_usage.message_total_cost(message_idx=-1),
            }
        self.tracker.step(**output_data)
