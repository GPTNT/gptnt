from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, override

import structlog
from google.genai.errors import ServerError
from pydantic_ai import (
    AgentRunError,
    ModelMessage,
    ModelResponse,
    RunUsage,
    UnexpectedModelBehavior,
)

from gptnt.players.actions import (
    AgentCallResult,
    AIResponseErrorType,
    DoNothingAction,
    SendMessageAction,
)
from gptnt.players.ai.messages.message_transformer import ensure_messages_have_valid_final_response
from gptnt.players.ai.output_validators import InvalidOutputFormatError

logger = structlog.get_logger()


class ExceptionRecoveryStrategy(ABC):
    """Handle various AI run exceptions in a graceful manner."""

    @abstractmethod
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        """Return whether this strategy can handle the given exception."""
        raise NotImplementedError

    @abstractmethod
    def recover(
        self,
        *,
        exception: Exception,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[Any]:
        """Handle the given exception and return a recovery result."""
        raise NotImplementedError


class DoNothingRecoveryStrategy(ExceptionRecoveryStrategy, ABC):
    """Mixin to return a DoNothingAction as recovery."""

    def recover_do_nothing(
        self,
        *,
        exception: Exception,
        ai_response_error: AIResponseErrorType,
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
            raw_output=raw_model_output,
            usage=RunUsage(),
            new_messages=new_messages,
            ai_response_error=ai_response_error,
        )


class GuardrailViolationRecovery(ExceptionRecoveryStrategy):
    """Handle situations where the model output is refused due to guardrail violations."""

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        return bool(
            isinstance(exception, AgentRunError)
            and "filtered due to the prompt triggering Azure OpenAI's content" in exception.message
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
        """Handle situations where the prompt is refused for some reason.

        In these cases, we want to tell the other agent to rephrase the prompt, BUT we do not want
        to count this as a new message in history to avoid it happening again.
        """
        logger.warning("Filtered due to content policy", error=exception)

        model_output = SendMessageAction(message="Can you rephrase that please?")

        return AgentCallResult(
            output=model_output,
            raw_output=raw_model_output,
            usage=RunUsage(),
            new_messages=[],
            ai_response_error=AIResponseErrorType.guardrail_violation,
        )


class ExceededMaxTokensRecovery(DoNothingRecoveryStrategy):
    """Handle situations where the model output is refused due to exceeding max tokens."""

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        return bool(
            isinstance(exception, UnexpectedModelBehavior)  # noqa: WPS222
            and "Exceeded maximum retries" in exception.message
            and new_messages
            and isinstance(new_messages[-1], ModelResponse)
            and new_messages[-1].finish_reason == "length"
        )

    @override
    def recover(
        self,
        *,
        exception: Exception,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[DoNothingAction]:
        logger.warning("Exceeded maximum tokens", error=str(exception))
        return self.recover_do_nothing(
            exception=exception,
            ai_response_error=AIResponseErrorType.max_tokens_exceeded,
            new_messages=new_messages,
            raw_model_output=raw_model_output,
        )


class InvalidFormatRecovery(DoNothingRecoveryStrategy):
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

        return bool(is_exceed_max_retries and finish_reason_not_length) or isinstance(
            exception, InvalidOutputFormatError
        )

    @override
    def recover(
        self,
        *,
        exception: Exception,
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
            ai_response_error=AIResponseErrorType.invalid_format,
            new_messages=new_messages,
            raw_model_output=raw_model_output,
        )


class SomethingNewWentWrongRecovery(DoNothingRecoveryStrategy):
    """Handle any other situations where something went wrong."""

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        return bool(isinstance(exception, AgentRunError))

    @override
    def recover(
        self,
        *,
        exception: Exception,
        new_messages: list[ModelMessage],
        raw_model_output: str | None = None,
        **kwargs: Any,
    ) -> AgentCallResult[DoNothingAction]:
        logger.exception(
            "SOMETHING NEW HAS GONE WRONG, defaulting to `DoNothing`", error=exception
        )
        return self.recover_do_nothing(
            exception=exception,
            ai_response_error=AIResponseErrorType.unknown,
            new_messages=new_messages,
            raw_model_output=raw_model_output,
        )


class GoogleServerErrorRecovery(DoNothingRecoveryStrategy):
    """Handle situations where Google API returns a 500 server error."""

    @override
    def can_handle(self, *, exception: Exception, new_messages: list[ModelMessage]) -> bool:
        return bool(isinstance(exception, ServerError))

    @override
    def recover(
        self,
        *,
        exception: Exception,
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
            ai_response_error=AIResponseErrorType.server_error,
            new_messages=new_messages,
            raw_model_output=raw_model_output,
        )


DEFAULT_RECOVERY_STRATEGIES = (
    GuardrailViolationRecovery(),
    ExceededMaxTokensRecovery(),
    InvalidFormatRecovery(),
    GoogleServerErrorRecovery(),
    SomethingNewWentWrongRecovery(),
)


@dataclass(kw_only=True)
class ExceptionRecoveryChain:
    """Chain of exception recovery strategies to handle AI exceptions.

    The chain will go through each strategy in order and use the first one that can handle the
    given exception.
    """

    strategies: Sequence[ExceptionRecoveryStrategy] = field(default=DEFAULT_RECOVERY_STRATEGIES)

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
