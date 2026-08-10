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
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol

from tests._cases.messages import TEST_TOKENS_PER_IMAGE, image_count

_FIXED_TIMESTAMP = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)


def _capabilities() -> PlayerCapabilities:
    return PlayerCapabilities(
        player_name="test-player",
        player_type="ai",
        structured_output_mode="prompted",
        interaction_location_method="coordinates",
        preserve_last_frame_for_n_turns=1,
        tokens_per_image=TEST_TOKENS_PER_IMAGE,
        usage_limits=UsageLimits(input_tokens_limit=6000),
    )


def _turn(index: int, *, input_tokens: int, text_chars: int = 0) -> list[ModelMessage]:
    """Build a single-frame turn with controllable measured and estimated
    sizes."""
    question = f"What should I do on turn {index}?"
    padded = question + "x" * max(text_chars - len(question), 0)
    return [
        ModelRequest(
            parts=[
                UserPromptPart(
                    content=[
                        TextPart(content=padded),
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


def _multi_frame_turn(
    index: int, *, frames: int, input_tokens: int, text_chars: int = 0
) -> list[ModelMessage]:
    """Build a turn with several frames in one user-prompt part.

    This matches gameplay input: all frames are sent in the current request, while later renders
    keep only the final frame from the part.
    """
    question = f"What should I do on turn {index}?"
    padded = question + "x" * max(text_chars - len(question), 0)
    return [
        ModelRequest(
            parts=[
                UserPromptPart(
                    content=[
                        TextPart(content=padded),
                        *[
                            BinaryContent(data=f"frame-{frame}".encode(), media_type="image/png")
                            for frame in range(frames)
                        ],
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


def test_render_composes_truncation_windowing_and_coercion() -> None:
    """Rendering truncates turns, windows images, and converts tool output."""
    protocol = PlayerProtocol(
        role="defuser", communication_style="sync", is_playing_alone=False, include_manual=False
    )
    capabilities = _capabilities()
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    conversation.record(
        [
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content=[
                            TextPart(content="padding " * 500),
                            BinaryContent(data=b"\x89PNG-fake", media_type="image/png"),
                        ],
                        timestamp=_FIXED_TIMESTAMP,
                    )
                ]
            ),
            ModelResponse(
                parts=[TextPart(content="Response for turn 0.")],
                usage=RequestUsage(input_tokens=100),
                timestamp=_FIXED_TIMESTAMP,
            ),
        ]
    )
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
                usage=RequestUsage(input_tokens=2000),
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

    rendered = conversation.render(capabilities)

    assert _texts(rendered) == [
        "What should I do on turn 1?",
        "Response for turn 1.",
        "What should I do on turn 2?",
        json.dumps(
            {"result": {"kind": "send_message", "data": {"message": "Cut the blue wire."}}}
        ),
    ]
    requests = [message for message in rendered if isinstance(message, ModelRequest)]
    assert image_count([requests[0]]) == 0
    assert image_count([requests[1]]) == 1


def _capabilities_and_protocol(
    *, limit: int | None, window: int, include_manual: bool
) -> tuple[PlayerCapabilities, PlayerProtocol]:
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
    return capabilities, protocol


def _recorded_turns(conversation: Conversation) -> int:
    return sum(not entry.pinned for entry in conversation.entries)


def _rendered_turns(messages: list[ModelMessage]) -> int:
    return sum(isinstance(message, ModelResponse) for message in messages)


def test_recorded_usage_truncates_the_render() -> None:
    """Recorded provider usage truncates the history returned by `render`.

    The store retains all 40 turns and the pinned manual. The rendered history omits only an old
    prefix of non-pinned turns.
    """
    capabilities, protocol = _capabilities_and_protocol(limit=5000, window=1, include_manual=True)
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(40):
        conversation.record(_turn(index, input_tokens=100 * (index + 1), text_chars=400))

    dropped = conversation.num_entries_dropped(capabilities)
    rendered = conversation.render(capabilities)

    assert 0 < _rendered_turns(rendered) < 40
    assert dropped > 0
    assert _rendered_turns(rendered) == _recorded_turns(conversation) - dropped
    assert _recorded_turns(conversation) == 40  # store is not mutated by render/truncation
    assert conversation.entries[0].pinned


def test_truncated_count_equals_turns_missing_from_render() -> None:
    """The reported truncation count equals the omitted turn count."""
    capabilities, protocol = _capabilities_and_protocol(limit=5000, window=1, include_manual=True)
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(40):
        conversation.record(_turn(index, input_tokens=100 * (index + 1), text_chars=400))

    missing = _recorded_turns(conversation) - _rendered_turns(conversation.render(capabilities))

    assert missing > 0
    assert conversation.num_entries_dropped(capabilities) == missing


def test_zero_usage_turn_does_not_break_truncation() -> None:
    """A zero-usage entry among measured entries does not affect truncation."""
    capabilities, protocol = _capabilities_and_protocol(limit=5000, window=1, include_manual=False)
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(20):
        input_tokens = 0 if index == 10 else 100 * (index + 1)
        conversation.record(_turn(index, input_tokens=input_tokens, text_chars=400))

    dropped = conversation.num_entries_dropped(capabilities)
    rendered = conversation.render(capabilities)

    assert 0 < dropped < _recorded_turns(conversation)
    assert _rendered_turns(rendered) == _recorded_turns(conversation) - dropped


def test_truncated_turns_do_not_reappear_after_a_smaller_provider_count() -> None:
    """A smaller provider count does not restore previously omitted turns."""
    capabilities, protocol = _capabilities_and_protocol(limit=1000, window=0, include_manual=False)
    capabilities = capabilities.model_copy(
        update={"tokens_per_image": 0, "max_observations_per_request": 0}
    )
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(5):
        conversation.record(_turn(index, input_tokens=0, text_chars=400))
    conversation.record(_turn(5, input_tokens=1200, text_chars=400))

    assert conversation.num_entries_dropped(capabilities) == 4
    assert _rendered_turns(conversation.render(capabilities)) == 2

    conversation.record(_turn(6, input_tokens=700, text_chars=400))

    assert conversation.num_entries_dropped(capabilities) == 4
    assert _rendered_turns(conversation.render(capabilities)) == 3


def test_latest_zero_usage_preserves_previously_omitted_turns() -> None:
    """A latest turn with zero usage does not restore previously omitted
    turns."""
    capabilities, protocol = _capabilities_and_protocol(limit=1000, window=0, include_manual=False)
    capabilities = capabilities.model_copy(
        update={"tokens_per_image": 0, "max_observations_per_request": 0}
    )
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(5):
        conversation.record(_turn(index, input_tokens=0, text_chars=400))
    conversation.record(_turn(5, input_tokens=1200, text_chars=400))
    assert conversation.num_entries_dropped(capabilities) == 4

    conversation.record(_turn(6, input_tokens=0, text_chars=400))

    assert conversation.num_entries_dropped(capabilities) == 4
    assert _rendered_turns(conversation.render(capabilities)) == 3


def test_repeated_render_does_not_drop_more_turns() -> None:
    """Repeated renders apply one provider measurement only once."""
    capabilities, protocol = _capabilities_and_protocol(limit=1000, window=0, include_manual=False)
    capabilities = capabilities.model_copy(
        update={"tokens_per_image": 0, "max_observations_per_request": 0}
    )
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(5):
        conversation.record(_turn(index, input_tokens=0, text_chars=400))
    conversation.record(_turn(5, input_tokens=1200, text_chars=400))

    first = conversation.render(capabilities)
    second = conversation.render(capabilities)

    assert _rendered_turns(first) == 2
    assert _rendered_turns(second) == 2
    assert conversation.num_entries_dropped(capabilities) == 4


def test_eviction_leaves_the_truncation_decision_and_usage_untouched() -> None:
    """Image eviction does not change usage or the omitted-entry count.

    Entries outside the image window are already estimated without images. Removing their stored
    image bytes therefore cannot change the truncation calculation.
    """
    capabilities, protocol = _capabilities_and_protocol(limit=5000, window=1, include_manual=False)
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(40):
        conversation.record(_turn(index, input_tokens=100 * (index + 1), text_chars=400))

    dropped_before = conversation.num_entries_dropped(capabilities)
    usage_before = [entry.usage.input_tokens for entry in conversation.entries]
    images_before = sum(image_count(entry.messages) for entry in conversation.entries)

    conversation.evict_observations(capabilities.preserve_last_frame_for_n_turns)

    assert dropped_before > 0
    assert conversation.num_entries_dropped(capabilities) == dropped_before
    assert [entry.usage.input_tokens for entry in conversation.entries] == usage_before
    assert images_before == 40
    assert sum(image_count(entry.messages) for entry in conversation.entries) == 1


def test_render_bounds_growth_and_windows_images() -> None:
    """Rendering limits both conversation turns and retained observation
    images."""
    capabilities, protocol = _capabilities_and_protocol(limit=5000, window=1, include_manual=False)
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(40):
        conversation.record(_turn(index, input_tokens=100 * (index + 1), text_chars=400))

    rendered = conversation.render(capabilities)

    assert 0 < _rendered_turns(rendered) < 20
    assert image_count(rendered) == 1


def test_morse_turn_of_sixteen_frames_collapses_to_one_image_in_render() -> None:
    """Rendering retains only the final image from a 16-frame prompt part.

    The stored entry retains all 16 images until it leaves the observation window.
    """
    capabilities, protocol = _capabilities_and_protocol(
        limit=100_000, window=1, include_manual=False
    )
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    conversation.record(_multi_frame_turn(0, frames=16, input_tokens=3400))

    rendered = conversation.render(capabilities)

    assert image_count(conversation.entries[-1].messages) == 16
    assert image_count(rendered) == 1


def test_eviction_of_a_morse_turn_does_not_shift_truncation() -> None:
    """Eviction does not change truncation after a 16-frame turn.

    Provider usage includes all 16 images. Eviction removes images only from older turns, whose
    estimates already exclude images, so the calculation remains unchanged.
    """
    capabilities, protocol = _capabilities_and_protocol(limit=5000, window=1, include_manual=False)
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(4):
        conversation.record(_turn(index, input_tokens=400 * (index + 1)))
    conversation.record(_multi_frame_turn(4, frames=16, input_tokens=3600))

    dropped_before = conversation.num_entries_dropped(capabilities)
    usage_before = [entry.usage.input_tokens for entry in conversation.entries]
    images_before = sum(image_count(entry.messages) for entry in conversation.entries)

    conversation.evict_observations(capabilities.preserve_last_frame_for_n_turns)

    assert conversation.num_entries_dropped(capabilities) == dropped_before
    assert [entry.usage.input_tokens for entry in conversation.entries] == usage_before
    assert images_before == 4 + 16
    assert sum(image_count(entry.messages) for entry in conversation.entries) == 16
    assert image_count(conversation.render(capabilities)) == 1


def test_long_monotonic_conversation_stays_bounded_and_keeps_pinned() -> None:
    """A 300-turn history stays bounded without omitting the pinned manual."""
    capabilities, protocol = _capabilities_and_protocol(limit=5000, window=1, include_manual=True)
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(300):
        conversation.record(_turn(index, input_tokens=100 * (index + 1), text_chars=400))

    rendered = conversation.render(capabilities)

    assert _recorded_turns(conversation) == 300
    assert 0 < _rendered_turns(rendered) < 40
    assert conversation.entries[0].pinned


def test_long_growing_conversation_with_multiframe_turns_stays_bounded() -> None:
    """Periodic 16-frame turns do not make rendered history grow without bound.

    The store retains all 200 turns. Each render keeps some recent turns and at most one image.
    """
    capabilities, protocol = _capabilities_and_protocol(limit=5000, window=1, include_manual=False)
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    rendered_turn_counts: list[int] = []
    for index in range(200):
        base = 100 * (index + 1)
        if index % 25 == 0:
            conversation.record(
                _multi_frame_turn(index, frames=16, input_tokens=base + 3000, text_chars=400)
            )
        else:
            conversation.record(_turn(index, input_tokens=base, text_chars=400))
        conversation.evict_observations(capabilities.preserve_last_frame_for_n_turns)
        rendered_turn_counts.append(_rendered_turns(conversation.render(capabilities)))

    rendered = conversation.render(capabilities)
    assert _recorded_turns(conversation) == 200
    assert 0 < max(rendered_turn_counts) < 40
    assert image_count(rendered) <= 1


def test_a_sixteen_frame_turn_can_require_dropping_most_older_turns() -> None:
    """A large current observation can require omitting most older turns.

    The provider count includes all 16 images, while older turns contribute only text after their
    images leave the observation window.
    """
    capabilities, protocol = _capabilities_and_protocol(limit=5000, window=1, include_manual=False)
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(8):
        conversation.record(_turn(index, input_tokens=300))

    dropped_before_large_turn = conversation.num_entries_dropped(capabilities)
    conversation.record(_multi_frame_turn(8, frames=16, input_tokens=300 + 3200))
    dropped_after_large_turn = conversation.num_entries_dropped(capabilities)

    assert dropped_before_large_turn == 0
    assert dropped_after_large_turn >= 5
