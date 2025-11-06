from dataclasses import dataclass, field
from typing import Union, override

import logfire
import structlog
from google.genai.errors import ServerError
from pydantic import ValidationError
from pydantic_ai import Agent, AgentRunError, UnexpectedModelBehavior
from pydantic_ai.models import Model

from gptnt.common.instrumentation import InstrumentationDataclassMixin
from gptnt.players.actions import (
    PlayerOutputType,
    SendMessageAction,
    SendMessageActionWithThoughts,
)
from gptnt.players.ai.message_history import AgentMessageInput, MessageHistory
from gptnt.players.ai.output_validators import (
    AgentOutput,
    InvalidOutputFormatError,
    structure_string_output,
)
from gptnt.players.metrics.episode_tracker import EpisodeTracker
from gptnt.players.metrics.structures import AIResponseErrorType
from gptnt.players.prompts.instructions import load_instructions_from_deps
from gptnt.players.prompts.reflection import ReflectionMessage, load_reflection_prompt
from gptnt.players.specification import PlayerCapabilities, PlayerDeps, PlayerProtocol

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ActionPredictor(InstrumentationDataclassMixin):
    """Predict actions to perform using AI agents/models to do so."""

    agent: Agent[PlayerDeps | None, PlayerOutputType | str]
    """The PydanticAI agent that the AI player uses."""

    capabilities: PlayerCapabilities

    tracker: EpisodeTracker = field(init=False, repr=False)
    protocol: PlayerProtocol = field(init=False, repr=False)
    message_history: MessageHistory = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Prepare agent."""
        self.agent._deps_type = PlayerDeps  # noqa: SLF001
        _ = self.agent.instructions(load_instructions_from_deps)

        super().__post_init__()

    @override
    def perform_instrumentation(self) -> None:
        logger.debug("Instrumenting AI player.")
        logfire.instrument_pydantic_ai(self.agent)  # pyright: ignore[reportCallIssue, reportArgumentType]

    @property
    def model_name(self) -> str:
        """Get the name of the model."""
        if isinstance(self.agent.model, str):
            return self.agent.model
        if isinstance(self.agent.model, Model):
            return self.agent.model.model_name
        raise ValueError("Model name not found")

    def configure_for_experiment(
        self, *, protocol: PlayerProtocol, message_history: MessageHistory, tracker: EpisodeTracker
    ) -> None:
        """Setup the agent for the current experiment."""
        self.protocol = protocol
        self.message_history = message_history
        self.tracker = tracker

    @logfire.instrument("Send request to agent", extract_args=False)
    async def send_request_to_agent(self, *, message_input: AgentMessageInput) -> AgentOutput:  # noqa: WPS213
        """Send a message to the AI.

        This will be the main way to send messages to the AI.
        """
        self.message_history.truncate_history_if_needed()
        ai_response_error = None

        try:  # noqa: WPS229, WPS225
            model_output = await self.agent.run(
                message_input,
                deps=self._agent_deps,
                output_type=self._agent_deps.output_type,
                message_history=self.message_history.to_history(),
            )
            model_output.output = structure_string_output(
                output=model_output.output, output_type=self._agent_deps.structured_output_type
            )
        except (InvalidOutputFormatError, ValidationError) as format_error:
            logger.warning(
                "Invalid output format from the agent.",
                error=format_error,
                message_input=message_input,
            )
            ai_response_error = AIResponseErrorType.invalid_format
            return AgentOutput.do_nothing()
        except AgentRunError as err:
            if "filtered due to the prompt triggering Azure OpenAI's content" in err.message:
                logger.warning("Filtered due to content policy", error=err)
                ai_response_error = AIResponseErrorType.guardrail_violation
            else:
                logger.exception(
                    "SOMETHING NEW HAS GONE WRONG, defaulting to `DoNothing`", error=err
                )
                ai_response_error = AIResponseErrorType.unknown
            return AgentOutput.do_nothing()
        except ServerError as server_err:
            logger.warning(
                "Server error occurred while running the agent.",
                error=server_err,
                message_input=message_input,
            )
            ai_response_error = AIResponseErrorType.server_error
            return AgentOutput.do_nothing()

        self.tracker.error_event_per_request.append(ai_response_error)
        # It should not be a string, like if its a string I will be very surprised because we are
        # using the output validator
        assert not isinstance(model_output.output, str)
        self.tracker.add_usage(model_output.usage())

        self.message_history.update(
            new_messages=model_output.new_messages(), usage=model_output.usage()
        )

        return AgentOutput.with_message_cleanup(
            output=model_output.output,
            usage=model_output.usage(),
            new_messages=model_output.new_messages(),
        )

    async def send_reflection_request(self, *, reflection_message: ReflectionMessage) -> None:
        """Send a reflection message to the agent."""
        reflection_prompt = load_reflection_prompt()

        try:
            model_output = await self.agent.run(
                [reflection_message, reflection_prompt],
                deps=self._agent_deps,
                # If the player supports structured output, then we give it the chance to use the
                # structured output for send message directly, otherwise we just let it be a string
                # and hope for the best with parsing it.
                output_type=(
                    Union[SendMessageAction | SendMessageActionWithThoughts | str]  # noqa: UP007
                    if self.capabilities.supports_structured_output
                    else str
                ),
                message_history=self.message_history.to_history(),
            )
        except UnexpectedModelBehavior:
            # We are raising an error here because reflection is not critical but we want to flag
            # it significantly. The problem is that the full exception log is blocking.
            logger.error(  # noqa: TRY400
                "Unexpected model behavior during reflection. Logging a default '<error>'."
            )
            model_output = SendMessageAction(message="<error>")

        if isinstance(model_output, SendMessageAction):
            response_as_action = model_output
        elif isinstance(model_output.output, SendMessageAction):
            response_as_action = model_output.output
        elif isinstance(model_output.output, str):  # pyright: ignore[reportUnnecessaryIsInstance]
            response_as_action = SendMessageAction(message=model_output.output)
        else:
            response_as_action = SendMessageAction(message=model_output.output.model_dump_json())

        self.tracker.add_reflection(message=response_as_action, role=self.protocol.role)

    @property
    def _agent_deps(self) -> PlayerDeps:
        """Get the agent dependencies."""
        return PlayerDeps(capabilities=self.capabilities, protocol=self.protocol)
