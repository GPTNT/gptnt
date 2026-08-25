from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Self, override

import httpx
import structlog
import tenacity
from google.genai.errors import ServerError as GoogleServerError
from pydantic_ai import (
    AgentRunError,
    ModelHTTPError,
    ModelMessage,
    ModelResponse,
    RunUsage,
    TextPart,
    UnexpectedModelBehavior,
)

from gptnt.players.actions import DoNothingAction, SendMessageAction
from gptnt.players.exceptions import (
    AIResponseErrorType,
    ExceededMaxOutputTokensError,
    InvalidOutputFormatError,
    InvalidResponseError,
    ReasoningParsingError,
)
from gptnt.players.result import AgentCallResult

logger = structlog.get_logger()


def usage_from_model_responses(messages: list[ModelMessage]) -> RunUsage:
    """Sum usage from provider responses captured before an agent run failed.

    PydanticAI raises some errors after the provider has already returned a billable response, for
    example when prompted output does not validate. In those cases there is no `AgentRunResult`
    to supply run usage, but `capture_run_messages` still gives us each response and its usage.

    `RunUsage.incr(RequestUsage)` does not increment the request count, so count each captured
    response explicitly as well as adding its token fields.
    """
    usage = RunUsage()
    for message in messages:
        if isinstance(message, ModelResponse):
            usage.requests += 1
            usage.incr(message.usage)
    return usage


def latest_model_response(messages: list[ModelMessage]) -> ModelResponse | None:
    """Return the latest captured provider response, if the request reached the provider."""
    return next(
        (message for message in reversed(messages) if isinstance(message, ModelResponse)), None
    )


def response_raw_output(response: ModelResponse | None) -> str | None:
    """Recover visible output, falling back to native thinking when no text was returned."""
    if response is None:
        return None
    return response.text or response.thinking


def ensure_messages_have_valid_final_response(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Append an empty `ModelResponse` when the messages hold none, so a run always ends in one."""
    if not messages:
        return messages
    if not any(isinstance(message, ModelResponse) for message in messages):
        messages.append(ModelResponse([TextPart("")]))
    return messages


@dataclass(kw_only=True)
class ExceptionRecoveryStrategy[ExceptionT: Exception, RecoveryOutputT](ABC):
    """Handle AI run exceptions in a graceful manner."""

    @abstractmethod
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        """Return whether this strategy can handle the exception."""
        raise NotImplementedError

    @abstractmethod
    def recover(
        self,
        *,
        exception: ExceptionT,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> RecoveryOutputT:
        """Handle the exception and return a recovery result."""
        raise NotImplementedError


@dataclass(kw_only=True)
class SendMessageRecoveryStrategy[ExceptionT: Exception](
    ExceptionRecoveryStrategy[ExceptionT, AgentCallResult[SendMessageAction]], ABC
):
    """Mixin to return a SendMessageAction as recovery."""


@dataclass(kw_only=True)
class DoNothingRecoveryStrategy[ExceptionT: Exception](
    ExceptionRecoveryStrategy[ExceptionT, AgentCallResult[DoNothingAction]], ABC
):
    """Mixin to return a DoNothingAction as recovery."""

    def recover_do_nothing(
        self,
        *,
        exception: Exception,
        ai_response_error: list[AIResponseErrorType],
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        thoughts: str | None = None,
        usage: RunUsage | None = None,
    ) -> AgentCallResult[DoNothingAction]:
        """Return a DoNothingAction as the recovery output."""
        response = latest_model_response(new_messages)

        if raw_model_output is None:
            raw_model_output = response_raw_output(response) or str(exception)
        if thoughts is None and response is not None:
            thoughts = response.thinking
        if usage is None:
            usage = usage_from_model_responses(new_messages)

        new_messages = ensure_messages_have_valid_final_response(new_messages)

        return AgentCallResult(
            output=DoNothingAction(),
            thoughts=thoughts,
            raw_output=raw_model_output,
            usage=usage,
            new_messages=new_messages,
            ai_response_error=ai_response_error,
        )


@dataclass(kw_only=True)
class GuardrailViolationRecovery(SendMessageRecoveryStrategy[AgentRunError]):
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

        Tell the other agent to revise the prompt, BUT do not count this as a new history message
        to avoid another refusal.
        """
        logger.warning("Filtered due to content policy", error=exception)

        model_output = SendMessageAction(message="Can you rephrase that please?")
        response = latest_model_response(new_messages)

        return AgentCallResult(
            output=model_output,
            thoughts=response.thinking if response is not None else None,  # noqa: WPS504
            raw_output=raw_model_output or response_raw_output(response),
            usage=usage_from_model_responses(new_messages),
            # Do not add a refused prompt to conversation history, or it may be refused again.
            new_messages=[],
            ai_response_error=[AIResponseErrorType.guardrail_violation],
        )


@dataclass(kw_only=True)
class ExceededMaxOutputTokensRecovery(
    DoNothingRecoveryStrategy[UnexpectedModelBehavior | ExceededMaxOutputTokensError]
):
    """Handle situations where the model output is refused due to exceeding max output tokens."""

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        response_ended_at_length = bool(
            new_messages
            and isinstance(new_messages[-1], ModelResponse)
            and new_messages[-1].finish_reason == "length"
        )
        token_limit_exception = bool(
            isinstance(exception, UnexpectedModelBehavior)
            and "model token limit" in exception.message.lower()
            and "exceeded" in exception.message.lower()
        )
        return (
            response_ended_at_length
            or token_limit_exception
            or isinstance(exception, ExceededMaxOutputTokensError)
        )

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

        response = latest_model_response(new_messages)
        thoughts = response.thinking if response is not None else None  # noqa: WPS504

        if raw_model_output is None and isinstance(exception, ExceededMaxOutputTokensError):
            raw_model_output = exception.output
        if raw_model_output is None and response is not None:
            raw_model_output = f"{response.thinking or ''}{response.text or ''}"

        # Collect before adding a synthetic response for conversation-history compatibility.
        usage = usage_from_model_responses(new_messages)

        new_messages = self.ensure_the_response_has_some_text(new_messages)

        return self.recover_do_nothing(
            exception=exception,
            ai_response_error=[AIResponseErrorType.max_output_tokens_exceeded],
            new_messages=new_messages,
            raw_model_output=raw_model_output,
            thoughts=thoughts,
            usage=usage,
        )

    def ensure_the_response_has_some_text(
        self, new_messages: list[ModelMessage]
    ) -> list[ModelMessage]:
        """Ensure there is something in the response.

        If we don't have any text in the response, it causes a huge knock-on effect on all future
        messages which causes everything to be broken and result in nothing but DoNothing's from
        the model.
        """
        response = next(
            (msg for msg in reversed(new_messages) if isinstance(msg, ModelResponse)), None
        )
        if not response:
            return [*new_messages, ModelResponse(parts=[TextPart(content="")])]

        if not response.text:
            # Add textpart to the response if its missing
            response.parts = [*response.parts, TextPart(content="")]
            new_messages[new_messages.index(response)] = response

        return new_messages


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


@dataclass(kw_only=True)
class InvalidFormatRecovery(
    DoNothingRecoveryStrategy[UnexpectedModelBehavior | InvalidOutputFormatError]
):
    """Handle situations where the model output is in an invalid format."""

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        exception_message = str(exception).lower()
        is_exceed_max_retries = bool(
            isinstance(exception, UnexpectedModelBehavior)
            and "exceeded maximum" in exception_message
            and "retries" in exception_message
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

        response_error = getattr(exception, "response_error", None)
        if response_error is None:
            response_error = [AIResponseErrorType.action_parsing_failed]

        return self.recover_do_nothing(
            exception=exception,
            ai_response_error=response_error,
            new_messages=new_messages,
            raw_model_output=raw_model_output,
        )


@dataclass(kw_only=True)
class SomethingNewWentWrongRecovery(
    DoNothingRecoveryStrategy[AgentRunError | httpx.HTTPStatusError]
):
    """Handle any other situations where something went wrong."""

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        return bool(isinstance(exception, (AgentRunError, httpx.HTTPStatusError)))

    @override
    def recover(
        self,
        *,
        exception: AgentRunError | httpx.HTTPStatusError,
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


@dataclass(kw_only=True)
class RequestQuotaExceededRecovery(DoNothingRecoveryStrategy[ModelHTTPError]):
    """Handle situations where the model provider returns a request quota exceeded error."""

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        return bool(
            isinstance(exception, ModelHTTPError)
            and (
                "quota" in exception.message.lower()
                or "resource exhausted" in exception.message.lower()
            )
        )

    @override
    def recover(
        self,
        *,
        exception: ModelHTTPError,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[DoNothingAction]:
        logger.warning("Request quota exceeded for the model provider.", error=exception)
        return self.recover_do_nothing(
            exception=exception,
            ai_response_error=[AIResponseErrorType.server_error],
            new_messages=new_messages,
            raw_model_output=raw_model_output,
        )


@dataclass(kw_only=True)
class ExhaustedRetriesRecovery(DoNothingRecoveryStrategy[tenacity.RetryError]):
    """Handle when retries are exhausted."""

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        return isinstance(exception, tenacity.RetryError)

    @override
    def recover(
        self,
        *,
        exception: tenacity.RetryError,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[DoNothingAction]:
        logger.warning("Retries are exhausted, returning as DoNothing.", error=exception)
        return self.recover_do_nothing(
            exception=exception,
            ai_response_error=[AIResponseErrorType.server_error],
            new_messages=new_messages,
            raw_model_output=raw_model_output,
        )


@dataclass(kw_only=True)
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


@dataclass(kw_only=True)
class ReflectionBrokenFormRecovery(SendMessageRecoveryStrategy[InvalidResponseError]):
    """Handle reflection being in an invalid form.

    If it's not following the structure, we want to just capture all of it.
    """

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        return bool(isinstance(exception, InvalidResponseError))

    @override
    def recover(
        self,
        *,
        exception: InvalidResponseError,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[SendMessageAction]:
        logger.warning(
            "Reflection output in invalid format. Capturing full output.", error=str(exception)
        )
        model_output = SendMessageAction(message=str(exception.output))
        response = latest_model_response(new_messages)
        usage = usage_from_model_responses(new_messages)
        new_messages = ensure_messages_have_valid_final_response(new_messages)

        return AgentCallResult(
            output=model_output,
            thoughts=response.thinking if response is not None else None,  # noqa: WPS504
            raw_output=raw_model_output or response_raw_output(response),
            usage=usage,
            new_messages=new_messages,
            ai_response_error=exception.response_error or [AIResponseErrorType.unknown],
        )


DEFAULT_RECOVERY_STRATEGIES = (
    GuardrailViolationRecovery(),
    RequestQuotaExceededRecovery(),
    ExhaustedRetriesRecovery(),
    ExceededMaxOutputTokensRecovery(),
    FailedReasoningParserRecovery(),
    InvalidFormatRecovery(),
    GoogleServerErrorRecovery(),
    SomethingNewWentWrongRecovery(),
)


@dataclass(kw_only=True)
class ReflectionOverrideRecovery(SendMessageRecoveryStrategy[Any]):
    """Capture and any all exceptions using other handlers and return them as an empty."""

    strategies: Sequence[ExceptionRecoveryStrategy[Any, AgentCallResult[Any]]]

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        return any(
            recovery_strategy.can_handle(exception=exception, new_messages=new_messages)
            for recovery_strategy in self.strategies
        )

    @override
    def recover(
        self,
        *,
        exception: Exception,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[SendMessageAction]:
        logger.warning(
            "Reflection failed with an unexpected error. Returning with a default '<error>'.",
            error=exception,
        )
        model_output = SendMessageAction(message="<error>")

        response_error = getattr(exception, "response_error", None)
        if response_error is None:
            response_error = [AIResponseErrorType.unknown]

        response = latest_model_response(new_messages)
        usage = usage_from_model_responses(new_messages)
        new_messages = ensure_messages_have_valid_final_response(new_messages)

        return AgentCallResult(
            output=model_output,
            thoughts=response.thinking if response is not None else None,  # noqa: WPS504
            raw_output=raw_model_output or response_raw_output(response),
            usage=usage,
            new_messages=new_messages,
            ai_response_error=response_error,
        )


@dataclass(kw_only=True)
class ExceptionRecoveryChain:
    """Chain of exception recovery strategies to handle AI exceptions.

    The chain will go through each strategy in order and use the first one that can handle the
    exception.
    """

    strategies: Sequence[ExceptionRecoveryStrategy[Any, AgentCallResult[Any]]]

    @classmethod
    def with_default_strategies(cls) -> Self:
        """Create an ExceptionRecoveryChain with the default strategies."""
        return cls(strategies=DEFAULT_RECOVERY_STRATEGIES)

    @classmethod
    def with_reflection_recovery(cls) -> Self:
        """Create an ExceptionRecoveryChain with the default strategies for reflection.

        First we try to capture the output in case it's broken. If not, we just return the default
        "<error>". Ofc, if the exception is an unknown, we want to error hard.
        """
        return cls(
            strategies=[
                ReflectionBrokenFormRecovery(),
                ReflectionOverrideRecovery(strategies=DEFAULT_RECOVERY_STRATEGIES),
            ]
        )

    def recover(
        self,
        *,
        exception: Exception,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[Any]:
        """Attempt to recover from the exception using the chain of strategies."""
        for strategy in self.strategies:
            if strategy.can_handle(exception=exception, new_messages=new_messages):
                return strategy.recover(
                    exception=exception,
                    new_messages=new_messages,
                    raw_model_output=raw_model_output,
                    **kwargs,
                )
        logger.exception(
            "No recovery strategy could handle the exception. Raising the original exception. EVERYBODY CRASH NOW!",
            error=exception,
        )
        raise exception
