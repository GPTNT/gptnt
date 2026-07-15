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

from gptnt.players.conversation import Conversation
from gptnt.players.deps import PlayerDeps
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
            elif isinstance(part, UserPromptPart) and isinstance(part.content, list):
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
    conversation = Conversation.begin(capabilities=deps.capabilities, protocol=deps.protocol)
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

    rendered = conversation.render(deps.capabilities)

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


def _deps(*, limit: int | None, window: int, include_manual: bool) -> PlayerDeps:
    capabilities = PlayerCapabilities(
        player_name="test-player",
        player_type="ai",
        structured_output_mode="prompted",
        interaction_location_method="coordinates",
        preserve_last_frame_for_n_turns=window,
        tokens_per_image=TEST_TOKENS_PER_IMAGE,
        usage_limits=UsageLimits(input_tokens_limit=limit),
    )
    protocol = PlayerProtocol(
        role="defuser",
        communication_style="sync",
        is_playing_alone=False,
        include_manual=include_manual,
    )
    return PlayerDeps(capabilities=capabilities, protocol=protocol)


def _recorded_turns(conversation: Conversation) -> int:
    return sum(not entry.pinned for entry in conversation.entries)


def _rendered_turns(messages: list[ModelMessage]) -> int:
    return sum(isinstance(message, ModelResponse) for message in messages)


def test_recorded_usage_truncates_the_render() -> None:
    """F1: recorded per-turn usage — not synthetic entries — truncates the rendered prompt.

    The `_truncation` unit tests hand-build entries; this checks the real public path: turns whose
    reported sizes grow past the budget make `render()` drop oldest turns while the pinned manual
    survives and the append-only store is left untouched.
    """
    deps = _deps(limit=1000, window=1, include_manual=True)
    conversation = Conversation.begin(capabilities=deps.capabilities, protocol=deps.protocol)
    for index in range(10):
        conversation.record(_turn(index, input_tokens=100 * (index + 1)))

    dropped = conversation.num_entries_dropped(deps.capabilities)
    rendered = conversation.render(deps.capabilities)

    assert dropped > 0
    assert _rendered_turns(rendered) == _recorded_turns(conversation) - dropped
    assert _recorded_turns(conversation) == 10  # store is not mutated by render/truncation
    assert conversation.entries[0].pinned  # manual survives


def test_truncated_count_equals_turns_missing_from_render() -> None:
    """F4: recorded `num_prompt_truncations` equals the turns actually absent from the prompt."""
    deps = _deps(limit=1000, window=1, include_manual=True)
    conversation = Conversation.begin(capabilities=deps.capabilities, protocol=deps.protocol)
    for index in range(10):
        conversation.record(_turn(index, input_tokens=100 * (index + 1)))

    missing = _recorded_turns(conversation) - _rendered_turns(
        conversation.render(deps.capabilities)
    )

    assert conversation.num_entries_dropped(deps.capabilities) == missing


def test_zero_usage_turn_does_not_break_truncation() -> None:
    """F3: a turn recorded with no usage (e.g. exception recovery) must not crash or over-drop."""
    deps = _deps(limit=1000, window=1, include_manual=False)
    conversation = Conversation.begin(capabilities=deps.capabilities, protocol=deps.protocol)
    for input_tokens in (300, 600, 0, 900, 1200):
        conversation.record(_turn(0, input_tokens=input_tokens))

    dropped = conversation.num_entries_dropped(deps.capabilities)
    rendered = conversation.render(deps.capabilities)

    assert 0 <= dropped < _recorded_turns(conversation)  # sane, and not everything dropped
    assert _rendered_turns(rendered) == _recorded_turns(conversation) - dropped


def test_render_bounds_growth_and_windows_images() -> None:
    """F1/#4: past the window and limit, render caps turns and keeps images only within the window.

    This is the guarantee the old `TokenAccountant` gave: context does not grow without bound, and
    observations survive only inside the frame window.
    """
    deps = _deps(limit=1000, window=1, include_manual=False)
    conversation = Conversation.begin(capabilities=deps.capabilities, protocol=deps.protocol)
    for index in range(15):
        conversation.record(_turn(index, input_tokens=100 * (index + 1)))

    rendered = conversation.render(deps.capabilities)

    assert _rendered_turns(rendered) < 15  # truncation bounds growth
    assert _image_count(rendered) == 1  # window=1 keeps the last frame only
