import datetime
import json

from pydantic_ai import (
    BinaryContent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RequestUsage,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.usage import UsageLimits

from gptnt.players.deps import PlayerDeps
from gptnt.players.history import Conversation
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol

from tests._cases.messages import TEST_TOKENS_PER_IMAGE

_FIXED_TIMESTAMP = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)


def _capabilities() -> PlayerCapabilities:
    return PlayerCapabilities(
        player_name="test-player",
        player_type="ai",
        structured_output_mode="prompted",
        interaction_location_method="coordinates",
        preserve_last_frame_for_n_turns=1,
        tokens_per_image=TEST_TOKENS_PER_IMAGE,
        usage_limits=UsageLimits(input_tokens_limit=400),
    )


def _turn(index: int, *, input_tokens: int) -> list[ModelMessage]:
    return [
        ModelRequest(
            parts=[
                UserPromptPart(
                    content=[
                        TextPart(content=f"What should I do on turn {index}?"),
                        BinaryContent(data=b"\x89PNG-fake", media_type="image/png"),
                    ],
                    timestamp=_FIXED_TIMESTAMP,
                )
            ]
        ),
        ModelResponse(
            parts=[TextPart(content=f"Response for turn {index}.")],
            usage=RequestUsage(input_tokens=input_tokens),
            timestamp=_FIXED_TIMESTAMP,
        ),
    ]


def _texts(messages: list[ModelMessage]) -> list[str]:
    collected: list[str] = []
    for message in messages:
        for part in message.parts:
            if isinstance(part, TextPart):
                collected.append(part.content)
            elif not isinstance(getattr(part, "content", None), str):
                collected.extend(
                    item.content for item in part.content if isinstance(item, TextPart)
                )
    return collected


def _image_count(messages: list[ModelMessage]) -> int:
    return sum(
        isinstance(item, BinaryContent)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart) and not isinstance(part.content, str)
        for item in part.content
    )


def test_render_composes_truncation_windowing_and_coercion() -> None:
    """Rendering truncates turns before it windows images and coerces structured output."""
    protocol = PlayerProtocol(
        role="defuser", communication_style="sync", is_playing_alone=False, include_manual=False
    )
    deps = PlayerDeps(capabilities=_capabilities(), protocol=protocol)
    conversation = Conversation.begin(deps)
    conversation.record(_turn(0, input_tokens=100))
    conversation.record(_turn(1, input_tokens=200))
    conversation.record(
        [
            _turn(2, input_tokens=300)[0],
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="final_result_send_message",
                        args='{"message":"Cut the blue wire."}',
                        tool_call_id="call-2",
                    )
                ],
                usage=RequestUsage(input_tokens=300),
                timestamp=_FIXED_TIMESTAMP,
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="final_result_send_message",
                        content="Final result processed.",
                        tool_call_id="call-2",
                        timestamp=_FIXED_TIMESTAMP,
                    )
                ]
            ),
        ]
    )

    rendered = conversation.render(deps)

    assert _texts(rendered) == [
        "What should I do on turn 1?",
        "Response for turn 1.",
        "What should I do on turn 2?",
        json.dumps(
            {"result": {"kind": "send_message", "data": {"message": "Cut the blue wire."}}}
        ),
    ]
    requests = [message for message in rendered if isinstance(message, ModelRequest)]
    assert _image_count([requests[0]]) == 0
    assert _image_count([requests[1]]) == 1
