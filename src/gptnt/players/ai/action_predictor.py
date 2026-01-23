from dataclasses import dataclass, field
from typing import override

import logfire
import structlog
from pydantic_ai import (
    Agent,
    AgentRunError,
    ModelMessage,
    ModelResponse,
    RunUsage,
    TextPart,
    capture_run_messages,
)
from pydantic_ai.models import Model

from gptnt.common.instrumentation import InstrumentationDataclassMixin
from gptnt.players.actions import (
    AgentCallResult,
    AIResponseErrorType,
    PlayerOutputType,
    SendMessageAction,
)
from gptnt.players.ai.exception_recovery import ExceptionRecoveryChain
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

    _exception_recovery: ExceptionRecoveryChain = field(
        default_factory=ExceptionRecoveryChain, repr=False
    )

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
    async def send_request_to_agent(  # noqa: WPS212, WPS231
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
            except Exception as exc:  # noqa: BLE001
                return self._exception_recovery.recover(
                    exception=exc,
                    new_messages=self._extract_new_messages(run_messages),
                    raw_model_output=None,
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
            return self._exception_recovery.recover(
                exception=structure_error,
                new_messages=model_output.new_messages(),
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
            hope for the best with parsing it.
        """
        reflection_prompt = load_reflection_prompt()

        with capture_run_messages() as run_messages:
            try:
                model_output = await self.agent.run(
                    [reflection_message, reflection_prompt],
                    deps=self._agent_deps,
                    output_type=str,
                    message_history=self.message_history.to_history(),
                )
            except AgentRunError:
                # We are catching the error here because reflection is not critical but we want to
                # flag it significantly. The problem is that outputting the full exception log is
                # blocking so we use logger.error instead of logger.exception.
                logger.error(  # noqa: TRY400
                    "Unexpected model behavior during reflection. Returning with a default '<error>'."
                )
                new_messages = self._extract_new_messages(run_messages)

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

        try:
            parsed_output = structure_string_output(
                output=model_output.output, output_type=SendMessageAction
            )
        except InvalidOutputFormatError:
            # If we fail to parse into SendMessageAction, we wrap the output into one
            parsed_output = SendMessageAction(message=model_output.output)

        return AgentCallResult(
            output=parsed_output,
            raw_output=str(model_output.response.parts),
            usage=model_output.usage(),
            new_messages=model_output.new_messages(),
            ai_response_error=None,
        )

    def _extract_new_messages(self, run_messages: list[ModelMessage]) -> list[ModelMessage]:
        """Extract the new messages from all the run messages."""
        return run_messages[len(self.message_history.to_history()) :]

    @property
    def _agent_deps(self) -> PlayerDeps:
        """Get the agent dependencies."""
        return PlayerDeps(capabilities=self.capabilities, protocol=self.protocol)
