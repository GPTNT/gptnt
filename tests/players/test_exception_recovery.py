from pydantic_ai import ModelMessage, ModelResponse, RequestUsage, TextPart, ThinkingPart

from gptnt.players.exception_recovery import (
    ExceededMaxOutputTokensRecovery,
    ReflectionBrokenFormRecovery,
    usage_from_model_responses,
)
from gptnt.players.exceptions import (
    AIResponseErrorType,
    ExceededMaxOutputTokensError,
    InvalidResponseError,
)


def _response(*, text: str = "visible", thinking: str = "private") -> ModelResponse:
    return ModelResponse(
        parts=[ThinkingPart(thinking), TextPart(text)],
        usage=RequestUsage(input_tokens=3, output_tokens=4),
        finish_reason="length",
    )


def test_usage_from_model_responses_preserves_billable_usage() -> None:
    messages: list[ModelMessage] = [_response(), _response()]

    usage = usage_from_model_responses(messages)

    assert usage.requests == 2
    assert usage.input_tokens == 6
    assert usage.output_tokens == 8


def test_token_limit_recovery_preserves_response_details() -> None:
    response = _response()
    messages: list[ModelMessage] = [response]
    error = ExceededMaxOutputTokensError(output="partial")
    strategy = ExceededMaxOutputTokensRecovery()

    result = strategy.recover(exception=error, new_messages=messages)

    assert result.usage.requests == 1
    assert result.usage.input_tokens == 3
    assert result.usage.output_tokens == 4
    assert result.thoughts == "private"
    assert result.raw_output == "partial"
    assert result.new_messages == [response]
    assert result.ai_response_error == [AIResponseErrorType.max_output_tokens_exceeded]


def test_reflection_recovery_preserves_response_and_history() -> None:
    response = _response()
    messages: list[ModelMessage] = [response]
    error = InvalidResponseError(output="fallback message")

    result = ReflectionBrokenFormRecovery().recover(exception=error, new_messages=messages)

    assert result.output.message == "fallback message"
    assert result.usage.requests == 1
    assert result.thoughts == "private"
    assert result.raw_output == "visible"
    assert result.new_messages == [response]
