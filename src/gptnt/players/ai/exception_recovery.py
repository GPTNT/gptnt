from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, override

import structlog
from google.genai.errors import ServerError as GoogleServerError
from pydantic_ai import (
    AgentRunError,
    ModelMessage,
    ModelResponse,
    RunUsage,
    UnexpectedModelBehavior,
)

from gptnt.players.actions import AgentCallResult, DoNothingAction, SendMessageAction
from gptnt.players.ai.messages.message_transformer import ensure_messages_have_valid_final_response
from gptnt.players.exceptions import (
    AIResponseErrorType,
    ExceededMaxOutputTokensError,
    InvalidOutputFormatError,
    ReasoningParsingError,
)

logger = structlog.get_logger()


class ExceptionRecoveryStrategy[ExceptionT: Exception](ABC):
    """Handle various AI run exceptions in a graceful manner."""

    @abstractmethod
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        """Return whether this strategy can handle the given exception."""
        raise NotImplementedError

    @abstractmethod
    def recover(
        self,
        *,
        exception: ExceptionT,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[Any]:
        """Handle the given exception and return a recovery result."""
        raise NotImplementedError


class DoNothingRecoveryStrategy[ExceptionT: Exception](ExceptionRecoveryStrategy[ExceptionT], ABC):
    """Mixin to return a DoNothingAction as recovery."""

    def recover_do_nothing(
        self,
        *,
        exception: Exception,
        ai_response_error: list[AIResponseErrorType],
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
    ) -> AgentCallResult[DoNothingAction]:
        """Return a DoNothingAction as the recovery output."""
        # If the raw model output isn't given, then we can
        if raw_model_output is None:
            if new_messages and isinstance(new_messages[-1], ModelResponse):
                raw_model_output = new_messages[-1].text
            else:
                raw_model_output = str(exception)

        new_messages = ensure_messages_have_valid_final_response(new_messages)

        return AgentCallResult(
            output=DoNothingAction(),
            thoughts=None,
            raw_output=raw_model_output,
            usage=RunUsage(),
            new_messages=new_messages,
            ai_response_error=ai_response_error,
        )


class GuardrailViolationRecovery(ExceptionRecoveryStrategy[AgentRunError]):
    """Handle situations where the model output is refused due to guardrail violations."""

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        return bool(
            isinstance(exception, AgentRunError)  # noqa: WPS222
            and (
                "filtered due to the prompt triggering azure openai's content"
                in exception.message.lower()
                or "your prompt was flagged as potentially violating our usage policy"
                in exception.message.lower()
                or "invalid prompt" in exception.message.lower()
                or "invalid_prompt" in exception.message.lower()
            )
        )

    @override
    def recover(
        self,
        *,
        exception: AgentRunError,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[SendMessageAction]:
        """Handle situations where the prompt is refused for some reason.

        In these cases, we want to tell the other agent to rephrase the prompt, BUT we do not want
        to count this as a new message in history to avoid it happening again.
        """
        logger.warning("Filtered due to content policy", error=exception)

        model_output = SendMessageAction(message="Can you rephrase that please?")

        return AgentCallResult(
            output=model_output,
            thoughts=None,
            raw_output=raw_model_output,
            usage=RunUsage(),
            new_messages=[],
            ai_response_error=[AIResponseErrorType.guardrail_violation],
        )


class ExceededMaxOutputTokensRecovery(
    DoNothingRecoveryStrategy[UnexpectedModelBehavior | ExceededMaxOutputTokensError]
):
    """Handle situations where the model output is refused due to exceeding max output tokens."""

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        return bool(
            new_messages
            and isinstance(new_messages[-1], ModelResponse)
            and new_messages[-1].finish_reason == "length"
        ) or isinstance(exception, ExceededMaxOutputTokensError)

    @override
    def recover(
        self,
        *,
        exception: UnexpectedModelBehavior | ExceededMaxOutputTokensError,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[DoNothingAction]:
        logger.warning("Exceeded maximum output tokens", error=str(exception))
        return self.recover_do_nothing(
            exception=exception,
            ai_response_error=[AIResponseErrorType.max_output_tokens_exceeded],
            new_messages=new_messages,
            raw_model_output=raw_model_output,
        )


class FailedReasoningParserRecovery(DoNothingRecoveryStrategy[ReasoningParsingError]):
    """Handle situations where the reasoning parser fails."""

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        return bool(isinstance(exception, ReasoningParsingError))

    @override
    def recover(
        self,
        *,
        exception: ReasoningParsingError,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[DoNothingAction]:
        logger.warning("Reasoning Parser failed", error=str(exception))
        return self.recover_do_nothing(
            exception=exception,
            ai_response_error=exception.response_error,
            new_messages=new_messages,
            raw_model_output=raw_model_output,
        )


class InvalidFormatRecovery(
    DoNothingRecoveryStrategy[UnexpectedModelBehavior | InvalidOutputFormatError]
):
    """Handle situations where the model output is in an invalid format."""

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        is_exceed_max_retries = bool(
            isinstance(exception, UnexpectedModelBehavior)
            and "Exceeded maximum retries" in exception.message
        )

        # Check if it is length, and then NOT that because we want to only handle non-length cases
        # of which there are LOADS of different variations.
        finish_reason_not_length = not bool(
            new_messages
            and isinstance(new_messages[-1], ModelResponse)
            and new_messages[-1].finish_reason == "length"
        )

        is_reasoning_parser_error = isinstance(exception, ReasoningParsingError)

        return bool(is_exceed_max_retries and finish_reason_not_length) or (
            isinstance(exception, InvalidOutputFormatError) and not is_reasoning_parser_error
        )

    @override
    def recover(
        self,
        *,
        exception: UnexpectedModelBehavior | InvalidOutputFormatError,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[DoNothingAction]:
        logger.warning(
            "Invalid output format from the agent.",
            raw_output=raw_model_output,
            error=str(exception),
        )

        return self.recover_do_nothing(
            exception=exception,
            # TODO: Make this error better
            ai_response_error=[AIResponseErrorType.unknown],
            new_messages=new_messages,
            raw_model_output=raw_model_output,
        )


class SomethingNewWentWrongRecovery(DoNothingRecoveryStrategy[AgentRunError]):
    """Handle any other situations where something went wrong."""

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        return bool(isinstance(exception, AgentRunError))

    @override
    def recover(
        self,
        *,
        exception: AgentRunError,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[DoNothingAction]:
        logger.exception(
            "SOMETHING NEW HAS GONE WRONG, defaulting to `DoNothing`", error=exception
        )
        return self.recover_do_nothing(
            exception=exception,
            ai_response_error=[AIResponseErrorType.unknown],
            new_messages=new_messages,
            raw_model_output=raw_model_output,
        )


class GoogleServerErrorRecovery(DoNothingRecoveryStrategy[GoogleServerError]):
    """Handle situations where Google API returns a 500 server error."""

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        return bool(isinstance(exception, GoogleServerError))

    @override
    def recover(
        self,
        *,
        exception: GoogleServerError,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[DoNothingAction]:
        logger.warning(
            "Google Server error occurred while running the agent.",
            error=exception,
            message_input=new_messages[-1] if new_messages else None,
        )
        return self.recover_do_nothing(
            exception=exception,
            ai_response_error=[AIResponseErrorType.server_error],
            new_messages=new_messages,
            raw_model_output=raw_model_output,
        )


class ReflectionRunRecovery(ExceptionRecoveryStrategy[AgentRunError]):
    """Handle situations where reflection fails.

    A reflection failure is not critical, so we want to just catch it and log it so we move on.
    """

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        return bool(isinstance(exception, AgentRunError))

    @override
    def recover(
        self,
        *,
        exception: AgentRunError,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[SendMessageAction]:
        logger.warning(
            "Unexpected model behavior during reflection. Returning with a default '<error>'."
        )
        model_output = SendMessageAction(message="<error>")

        return AgentCallResult(
            output=model_output,
            thoughts=None,
            raw_output=raw_model_output,
            usage=RunUsage(),
            new_messages=[],
            ai_response_error=[AIResponseErrorType.unknown],
        )


class ReflectionFormatRecovery(ExceptionRecoveryStrategy[InvalidOutputFormatError]):
    """Handle reflection being in an invalid format.

    If it's not following the structure, we want to just capture all of it.
    """

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        return bool(isinstance(exception, InvalidOutputFormatError))

    @override
    def recover(
        self,
        *,
        exception: InvalidOutputFormatError,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[SendMessageAction]:
        logger.warning(
            "Reflection output in invalid format. Capturing full output.", error=str(exception)
        )
        model_output = SendMessageAction(message=str(exception.output))

        return AgentCallResult(
            output=model_output,
            thoughts=None,
            raw_output=raw_model_output,
            usage=RunUsage(),
            new_messages=[],
            # TODO: Make this error better
            ai_response_error=[AIResponseErrorType.unknown],
        )


DEFAULT_RECOVERY_STRATEGIES = (
    GuardrailViolationRecovery(),
    ExceededMaxOutputTokensRecovery(),
    FailedReasoningParserRecovery(),
    InvalidFormatRecovery(),
    GoogleServerErrorRecovery(),
    SomethingNewWentWrongRecovery(),
)

DEFAULT_REFLECTION_RECOVERY_STRATEGIES = (
    ReflectionFormatRecovery(),
    ReflectionRunRecovery(),
    SomethingNewWentWrongRecovery(),
)


@dataclass(kw_only=True)
class ExceptionRecoveryChain:
    """Chain of exception recovery strategies to handle AI exceptions.

    The chain will go through each strategy in order and use the first one that can handle the
    given exception.
    """

    strategies: Sequence[ExceptionRecoveryStrategy[Any]] = field(
        default=DEFAULT_RECOVERY_STRATEGIES
    )

    def recover(
        self,
        *,
        exception: Exception,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[Any]:
        """Attempt to recover from the given exception using the chain of strategies."""
        for strategy in self.strategies:
            if strategy.can_handle(exception=exception, new_messages=new_messages):
                return strategy.recover(
                    exception=exception,
                    new_messages=new_messages,
                    raw_model_output=raw_model_output,
                    **kwargs,
                )

        raise exception


def create_reflection_recovery_chain() -> ExceptionRecoveryChain:
    """Create the default reflection recovery chain."""
    return ExceptionRecoveryChain(strategies=DEFAULT_REFLECTION_RECOVERY_STRATEGIES)
