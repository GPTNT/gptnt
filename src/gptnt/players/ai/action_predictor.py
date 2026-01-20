from dataclasses import dataclass, field
from typing import override

import logfire
import structlog
from google.genai.errors import ServerError
from pydantic import ValidationError
from pydantic_ai import (
    Agent,
    AgentRunError,
    ModelMessage,
    ModelResponse,
    NativeOutput,
    RunUsage,
    TextPart,
    UnexpectedModelBehavior,
    capture_run_messages,
)
from pydantic_ai.models import Model

from gptnt.common.instrumentation import InstrumentationDataclassMixin
from gptnt.players.actions import (
    AgentCallResult,
    AIResponseErrorType,
    DoNothingAction,
    PlayerOutputType,
    SendMessageAction,
)
from gptnt.players.ai.message_history import (
    AgentMessageInput,
    MessageHistory,
    coerce_tool_output_into_native_output,
)
from gptnt.players.ai.output_validators import InvalidOutputFormatError, structure_string_output
from gptnt.players.specification import PlayerCapabilities, PlayerDeps, PlayerProtocol
from gptnt.prompts.instructions import load_instructions_from_deps
from gptnt.prompts.reflection import load_reflection_prompt

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ActionPredictor(InstrumentationDataclassMixin):
    """Predict actions to perform using AI agents/models to do so."""

    agent: Agent[PlayerDeps | None, PlayerOutputType | str]
    """The PydanticAI agent that the AI player uses."""

    capabilities: PlayerCapabilities

    protocol: PlayerProtocol = field(init=False, repr=False)
    message_history: MessageHistory = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Prepare agent.

        These can only be done here because we init agents with Hydra.
        """
        self.agent._deps_type = PlayerDeps  # noqa: SLF001

        # TODO: I think we can provide instruction functions to the init now so this should be
        #       reworked to use that instead, but that's just a refactoring thing so for now we
        #       don't bother.
        # Not sure why this is complaining because it used to be fine, but ok
        _ = self.agent.instructions(load_instructions_from_deps)  # pyright: ignore[reportCallIssue, reportArgumentType]

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
        self, *, protocol: PlayerProtocol, message_history: MessageHistory
    ) -> None:
        """Setup the agent for the current experiment."""
        self.protocol = protocol
        self.message_history = message_history

    @logfire.instrument("Send request to agent", extract_args=False)
    async def send_request_to_agent(  # noqa: WPS212, WPS231, PLR0911
        self, *, message_input: AgentMessageInput
    ) -> AgentCallResult[PlayerOutputType]:
        """Send a message to the AI.

        This will be the main way to send messages to the AI.
        """
        self.message_history.truncate_history_if_needed()
        with capture_run_messages() as run_messages:
            try:
                model_output = await self.agent.run(
                    message_input,
                    deps=self._agent_deps,
                    output_type=self._agent_deps.output_type,
                    message_history=self.message_history.to_history(),
                )
            except ValidationError as format_error:
                logger.warning(
                    "Invalid output format from the agent.",
                    error=format_error,
                    message_input=message_input,
                )
                return self._pretend_model_wants_do_nothing(
                    all_messages=run_messages,
                    ai_response_error=AIResponseErrorType.invalid_format,
                    raw_model_output=format_error.json(include_url=False),
                )
            except AgentRunError as err:
                if "filtered due to the prompt triggering Azure OpenAI's content" in err.message:
                    logger.warning("Filtered due to content policy", error=err)
                    return self._handle_prompt_refusal(
                        ai_response_error=AIResponseErrorType.guardrail_violation
                    )

                # If it's a formatting error due to maxing out the output token limit,
                # we want to handle that specifically too
                if (
                    isinstance(err, UnexpectedModelBehavior)
                    and "Exceeded maximum retries" in err.message
                    and run_messages[-1].finish_reason == "length"  # pyright: ignore[reportAttributeAccessIssue]
                ):
                    logger.warning(
                        "Exceeded maximum retries, meaning output is invalid", error=str(err)
                    )
                    return self._pretend_model_wants_do_nothing(
                        all_messages=run_messages,
                        ai_response_error=AIResponseErrorType.max_tokens_exceeded,
                    )

                logger.exception(
                    "SOMETHING NEW HAS GONE WRONG, defaulting to `DoNothing`", error=err
                )
                return self._pretend_model_wants_do_nothing(
                    all_messages=run_messages, ai_response_error=AIResponseErrorType.unknown
                )
            except ServerError as server_err:
                logger.warning(
                    "Server error occurred while running the agent.",
                    error=server_err,
                    message_input=message_input,
                )
                return self._pretend_model_wants_do_nothing(
                    all_messages=run_messages, ai_response_error=AIResponseErrorType.server_error
                )

        try:
            model_output.output = structure_string_output(
                output=model_output.output, output_type=self._agent_deps.structured_output_type
            )
        except InvalidOutputFormatError as structure_error:
            logger.warning(
                "Invalid output format from the agent after structuring.",
                error=structure_error,
                message_input=message_input,
            )
            return self._pretend_model_wants_do_nothing(
                all_messages=model_output.all_messages(),
                ai_response_error=AIResponseErrorType.invalid_format,
                raw_model_output=structure_error.output,
            )

        # Convert tool outputs to NativeOutput if needed
        new_messages = coerce_tool_output_into_native_output(model_output.new_messages())

        return AgentCallResult(
            output=model_output.output,
            raw_output=str(model_output.response.parts),
            usage=model_output.usage(),
            new_messages=new_messages,
            ai_response_error=None,
        )

    async def send_reflection_request(
        self, *, reflection_message: str
    ) -> AgentCallResult[SendMessageAction]:
        """Send a reflection message to the agent.

        Importantly, we do not care if the reflection fails, we just want to log it and move on.

        For handling structured outputs:
            If the player supports structured output, then we give it the chance to use the
            structured output for send message directly, otherwise we just let it be a string and
            hope for the best with parsing it. Also, we use NativeOutput here because if it
            supports structured output, it should be able to do NativeOutput.
        """
        reflection_prompt = load_reflection_prompt()

        with capture_run_messages() as run_messages:
            try:
                model_output = await self.agent.run(
                    [reflection_message, reflection_prompt],
                    deps=self._agent_deps,
                    output_type=(
                        NativeOutput([SendMessageAction, str])
                        if self.capabilities.use_structured_outputs
                        and self.capabilities.structured_output_mode == "native"
                        else str
                    ),
                    message_history=self.message_history.to_history(),
                )
            except AgentRunError:
                # We are catching the error here because reflection is not critical but we want to
                # flag it significantly. The problem is that outputting the full exception log is
                # blocking so we use logger.error instead of logger.exception.
                logger.error(  # noqa: TRY400
                    "Unexpected model behavior during reflection. Returning with a default '<error>'."
                )
                num_new_messages = len(run_messages) - len(self.message_history.to_history())
                new_messages = run_messages[-num_new_messages:]

                model_output = SendMessageAction(message="<error>")
                return AgentCallResult(
                    output=model_output,
                    raw_output=None,
                    usage=RunUsage(),
                    new_messages=[
                        *new_messages,
                        ModelResponse(parts=[TextPart(model_output.text_part_dump())]),
                    ],
                    ai_response_error=AIResponseErrorType.unknown,
                )

        if not isinstance(model_output.output, SendMessageAction):
            model_output.output = SendMessageAction(message=str(model_output.output))

        return AgentCallResult(
            output=model_output.output,
            raw_output=str(model_output.response.parts),
            usage=model_output.usage(),
            new_messages=model_output.new_messages(),
            ai_response_error=None,
        )

    def _pretend_model_wants_do_nothing(
        self,
        *,
        all_messages: list[ModelMessage],
        ai_response_error: AIResponseErrorType,
        raw_model_output: str | None = None,
    ) -> AgentCallResult[DoNothingAction]:
        """Replace the response with a do nothing.

        Initially, this was implemented by comparing history lengths but that ended up being
        brittle and multiple responses got through. So as a result, we do things in a more robust
        way.
        """
        # If the last message is already a model response, we need to pop all the consecutive
        # responses from the end to make sure there are none left.
        cutoff_index = len(all_messages)
        while cutoff_index > 0 and isinstance(all_messages[cutoff_index - 1], ModelResponse):
            cutoff_index -= 1

        # Keep all messages up to (but not including) the trailing ModelResponse objects.
        message_history_with_new_request = all_messages[:cutoff_index]

        # Create the do nothing response
        model_output = DoNothingAction()
        model_response = ModelResponse(parts=[TextPart(model_output.text_part_dump())])

        return AgentCallResult(
            output=model_output,
            raw_output=raw_model_output,
            usage=RunUsage(),
            new_messages=[*message_history_with_new_request, model_response],
            ai_response_error=ai_response_error,
        )

    def _handle_prompt_refusal(
        self, *, ai_response_error: AIResponseErrorType, raw_model_output: str | None = None
    ) -> AgentCallResult[SendMessageAction]:
        """Handle situations where the prompt is refused for some reason.

        In these cases, we want to tell the other agent to rephrase the prompt, BUT we do not want
        to count this as a new message in history to avoid it happening again.
        """
        model_output = SendMessageAction(message="Can you rephrase that please?")

        return AgentCallResult(
            output=model_output,
            raw_output=raw_model_output,
            usage=RunUsage(),
            new_messages=[],
            ai_response_error=ai_response_error,
        )

    @property
    def _agent_deps(self) -> PlayerDeps:
        """Get the agent dependencies."""
        return PlayerDeps(capabilities=self.capabilities, protocol=self.protocol)
