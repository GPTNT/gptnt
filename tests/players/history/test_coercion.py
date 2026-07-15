import datetime
import json

from pydantic_ai import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.messages import ModelMessagesTypeAdapter

from gptnt.players.conversation._coercion import coerce_tool_output_into_native_output

_FIXED_TIMESTAMP = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)


def test_coercion_rewrites_tool_calls_and_removes_tool_returns() -> None:
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="Prompt", timestamp=_FIXED_TIMESTAMP)]),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="final_result_send_message",
                    args='{"message":"Cut the blue wire."}',
                    tool_call_id="call-1",
                )
            ],
            timestamp=_FIXED_TIMESTAMP,
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="final_result_send_message",
                    content="Final result processed.",
                    tool_call_id="call-1",
                    timestamp=_FIXED_TIMESTAMP,
                )
            ]
        ),
    ]
    before = ModelMessagesTypeAdapter.dump_json(messages)

    coerced = coerce_tool_output_into_native_output(messages)

    assert len(coerced) == 2
    assert isinstance(coerced[1], ModelResponse)
    assert coerced[1].parts == [
        TextPart(
            content=json.dumps(
                {"result": {"kind": "send_message", "data": {"message": "Cut the blue wire."}}}
            )
        )
    ]
    assert ModelMessagesTypeAdapter.dump_json(messages) == before
