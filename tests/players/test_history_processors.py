import datetime

import pytest
from pydantic_ai import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RequestUsage,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from gptnt.players.ai.message_history import coerce_tool_output_into_native_output


@pytest.fixture
def messages() -> list[ModelMessage]:
    return [
        ModelRequest(
            parts=[
                UserPromptPart(
                    content="roll down ",
                    timestamp=datetime.datetime(
                        2025, 12, 4, 19, 33, 59, 979613, tzinfo=datetime.UTC
                    ),
                )
            ],
            run_id="3646f60f-ae3c-43cb-82a0-b87025f4c41b",
        ),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="final_result_InteractGameActionWithThoughtsSingleAlphabetLetter",
                    args='{"action":"down"}',
                    tool_call_id="call_JDbp0oRA7ZgojQoYY121Qw1F",
                )
            ],
            usage=RequestUsage(
                input_tokens=343,
                output_tokens=673,
                details={
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 640,
                    "rejected_prediction_tokens": 0,
                },
            ),
            model_name="gpt-5-2025-08-07",
            timestamp=datetime.datetime(2025, 12, 4, 19, 34, 3, tzinfo=datetime.UTC),
            provider_name="openai",
            provider_details={"finish_reason": "tool_calls"},
            provider_response_id="chatcmpl-Cj9NTmHlG4ZC17oMWG29pFnInrFGd",
            finish_reason="tool_call",
            run_id="3646f60f-ae3c-43cb-82a0-b87025f4c41b",
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="final_result_InteractGameActionWithThoughtsSingleAlphabetLetter",
                    content="Final result processed.",
                    tool_call_id="call_JDbp0oRA7ZgojQoYY121Qw1F",
                    timestamp=datetime.datetime(
                        2025, 12, 4, 19, 34, 16, 407597, tzinfo=datetime.UTC
                    ),
                )
            ],
            run_id="3646f60f-ae3c-43cb-82a0-b87025f4c41b",
        ),
        ModelRequest(
            parts=[
                UserPromptPart(
                    content="roll up now ",
                    timestamp=datetime.datetime(
                        2025, 12, 4, 19, 34, 16, 427518, tzinfo=datetime.UTC
                    ),
                )
            ],
            run_id="514dbb2e-2fb1-47a0-8385-e18a6642e047",
        ),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="final_result_InteractGameActionWithThoughtsSingleAlphabetLetter",
                    args='{"action":"up"}',
                    tool_call_id="call_bStBnQSSOELOJbyvA5EK6Izk",
                )
            ],
            usage=RequestUsage(
                input_tokens=403,
                output_tokens=545,
                details={
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 512,
                    "rejected_prediction_tokens": 0,
                },
            ),
            model_name="gpt-5-2025-08-07",
            timestamp=datetime.datetime(2025, 12, 4, 19, 34, 17, tzinfo=datetime.UTC),
            provider_name="openai",
            provider_details={"finish_reason": "tool_calls"},
            provider_response_id="chatcmpl-Cj9NhRZAvEogtizdiG9mCmZ78UMrB",
            finish_reason="tool_call",
            run_id="514dbb2e-2fb1-47a0-8385-e18a6642e047",
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="final_result_InteractGameActionWithThoughtsSingleAlphabetLetter",
                    content="Final result processed.",
                    tool_call_id="call_bStBnQSSOELOJbyvA5EK6Izk",
                    timestamp=datetime.datetime(
                        2025, 12, 4, 19, 34, 32, 590159, tzinfo=datetime.UTC
                    ),
                )
            ],
            run_id="514dbb2e-2fb1-47a0-8385-e18a6642e047",
        ),
    ]


def test_converting_tool_output_to_native_works(messages: list[ModelMessage]) -> None:
    after = coerce_tool_output_into_native_output(messages)
    for message in after:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                assert not isinstance(part, ToolReturnPart)
        if isinstance(message, ModelResponse):
            for part in message.parts:
                assert not isinstance(part, ToolCallPart)
