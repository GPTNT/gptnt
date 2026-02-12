from dataclasses import dataclass, field
from typing import Any, override

import logfire
import structlog
from pydantic_ai import Agent, ModelMessage, capture_run_messages
from pydantic_ai.models import Model

from gptnt.common.instrumentation import InstrumentationDataclassMixin
from gptnt.players.actions import AgentCallResult, PlayerOutputType, SendMessageAction
from gptnt.players.ai.exception_recovery import (
    ExceptionRecoveryChain,
    create_reflection_recovery_chain,
)
from gptnt.players.ai.input_builder import AgentMessageInput
from gptnt.players.ai.messages.message_history import MessageHistory
from gptnt.players.deps import PlayerDeps, load_instructions_from_deps
from gptnt.players.exceptions import ExceededMaxOutputTokensError
from gptnt.players.reasoning_parser.reasoning_parser import ReasoningParser
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol
from gptnt.prompts.reflection import load_reflection_prompt

logger = structlog.get_logger()


async def execute_request[DepsT, ModelOutputT, ParserOutputT](
    message_input: AgentMessageInput,
    *,
    agent: Agent[DepsT, ModelOutputT],
    reasoning_parser: ReasoningParser[ModelOutputT, ParserOutputT],
    deps: DepsT,
    message_history: list[ModelMessage] | None = None,
    model_output_type: Any | None = None,
    parser_output_type: type[ParserOutputT] | None = None,
) -> AgentCallResult[ParserOutputT]:
    """Send a request to the agent and parse any outputs.

    Handle any and all exceptions OUTSIDE OF THIS FUNCTION PLEASE.
    """
    model_output = await agent.run(
        message_input, deps=deps, output_type=model_output_type, message_history=message_history
    )
    if model_output.response.finish_reason == "length":
        full_output = ""
        if model_output.response.thinking:
            full_output += model_output.response.thinking
        if model_output.response.text:
            full_output += model_output.response.text
        raise ExceededMaxOutputTokensError(output=full_output)

    # importantly, while the model might not need to return a structured output type, we still
    # need to parse out the final action correctly
    parsed_output = reasoning_parser(model_output, output_type=parser_output_type)
    return parsed_output


@dataclass(kw_only=True)
class ActionPredictor(InstrumentationDataclassMixin):
    """Predict actions to perform using AI agents/models to do so."""

    agent: Agent[PlayerDeps | None, PlayerOutputType | str]
    """The PydanticAI agent that the AI player uses."""

    capabilities: PlayerCapabilities

    reasoning_parser: ReasoningParser[Any, Any] = field(init=False, repr=False)

    protocol: PlayerProtocol = field(init=False, repr=False)
    message_history: MessageHistory = field(init=False, repr=False)

    exception_recovery: ExceptionRecoveryChain = field(
        default_factory=ExceptionRecoveryChain, repr=False
    )
    reflection_exception_recovery: ExceptionRecoveryChain = field(
        default_factory=create_reflection_recovery_chain, repr=False
    )

    def __post_init__(self) -> None:
        """Prepare agent.

        These can only be done here because we init agents with Hydra.
        """
        self.reasoning_parser = self.capabilities.reasoning_parser

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
        self.message_history.remove_observations_from_previous_messages()
        self.message_history.truncate_history_if_needed()

        with capture_run_messages() as run_messages:
            try:
                return await execute_request(
                    message_input,
                    agent=self.agent,
                    reasoning_parser=self.reasoning_parser,
                    deps=self._agent_deps,
                    message_history=self.message_history.to_history(),
                    model_output_type=self._agent_deps.output_type,
                    parser_output_type=self._agent_deps.structured_output_type,
                )
            except Exception as exc:  # noqa: BLE001
                return self.exception_recovery.recover(
                    exception=exc,
                    new_messages=self._extract_new_messages(run_messages),
                    raw_model_output=None,
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
        reflection_prompt = load_reflection_prompt(self._agent_deps.capabilities)

        with capture_run_messages() as run_messages:
            try:
                return await execute_request(
                    [reflection_message, reflection_prompt],
                    agent=self.agent,
                    reasoning_parser=self.reasoning_parser,
                    deps=self._agent_deps,
                    message_history=self.message_history.to_history(),
                    model_output_type=str,
                    parser_output_type=SendMessageAction,
                )
            except Exception as exc:  # noqa: BLE001
                return self.reflection_exception_recovery.recover(
                    exception=exc,
                    new_messages=self._extract_new_messages(run_messages),
                    raw_model_output=None,
                )

    def _extract_new_messages(self, run_messages: list[ModelMessage]) -> list[ModelMessage]:
        """Extract the new messages from all the run messages."""
        return run_messages[len(self.message_history.to_history()) :]

    @property
    def _agent_deps(self) -> PlayerDeps:
        """Get the agent dependencies."""
        return PlayerDeps(capabilities=self.capabilities, protocol=self.protocol)
