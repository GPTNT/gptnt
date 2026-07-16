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
        usage_limits=UsageLimits(input_tokens_limit=5000),
    )


def _turn(index: int, *, input_tokens: int, text_chars: int = 0) -> list[ModelMessage]:
    """A single-frame turn. `text_chars` pads the prompt so its estimated size is controllable.

    Real turns carry text roughly in proportion to their token size; `text_chars` lets a test give
    a turn a known size when dropped, since truncation sizes a dropped turn by its content.
    """
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
    """A turn that packs `frames` images into one `UserPromptPart`, as morse/simon turns do.

    Mirrors `input_builder`: many `BinaryContent`s in a single part, the last standing in for the
    set-of-marks frame. The recorded usage covers all the frames, because the model is sent all of
    them live before any windowing applies.
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
    """Rendering truncates turns before it windows images and coerces structured output."""
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
    """Recorded per-turn usage — not synthetic entries — truncates the rendered prompt.

    The `_truncation` unit tests hand-build entries; this checks the real public path: forty turns
    whose content and sizes grow past the budget make `render()` drop the oldest ones while the
    pinned manual survives, the append-only store is untouched, and recent turns are kept.
    """
    capabilities, protocol = _capabilities_and_protocol(limit=5000, window=1, include_manual=True)
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(40):
        conversation.record(_turn(index, input_tokens=100 * (index + 1), text_chars=400))

    dropped = conversation.num_entries_dropped(capabilities)
    rendered = conversation.render(capabilities)

    assert 0 < _rendered_turns(rendered) < 40  # some turns dropped, some recent ones kept
    assert dropped > 0
    assert _rendered_turns(rendered) == _recorded_turns(conversation) - dropped
    assert _recorded_turns(conversation) == 40  # store is not mutated by render/truncation
    assert conversation.entries[0].pinned  # manual survives


def test_truncated_count_equals_turns_missing_from_render() -> None:
    """Recorded `num_prompt_truncations` equals the turns actually absent from the prompt."""
    capabilities, protocol = _capabilities_and_protocol(limit=5000, window=1, include_manual=True)
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(40):
        conversation.record(_turn(index, input_tokens=100 * (index + 1), text_chars=400))

    missing = _recorded_turns(conversation) - _rendered_turns(conversation.render(capabilities))

    assert missing > 0  # the scenario truncates, so the invariant is not vacuous
    assert conversation.num_entries_dropped(capabilities) == missing


def test_zero_usage_turn_does_not_break_truncation() -> None:
    """A turn recorded with no usage (e.g. exception recovery) must not crash or over-drop."""
    capabilities, protocol = _capabilities_and_protocol(limit=5000, window=1, include_manual=False)
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(20):
        input_tokens = 0 if index == 10 else 100 * (index + 1)
        conversation.record(_turn(index, input_tokens=input_tokens, text_chars=400))

    dropped = conversation.num_entries_dropped(capabilities)
    rendered = conversation.render(capabilities)

    assert 0 < dropped < _recorded_turns(conversation)  # truncates, but never drops the newest
    assert _rendered_turns(rendered) == _recorded_turns(conversation) - dropped


def test_eviction_leaves_the_truncation_decision_and_usage_untouched() -> None:
    """Evicting image bytes must not move the truncation decision, because it anchors on usage.

    Truncation reads the latest turn's recorded usage for its anchor and sizes aged turns by their
    text alone — their images have already left the window. `evict_observations` strips those
    aged image bytes and leaves every entry's usage untouched, so the drop count is the same before
    and after, even though the stored image bytes really did go (10 turns' images down to one).
    """
    capabilities, protocol = _capabilities_and_protocol(limit=5000, window=1, include_manual=False)
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(40):
        conversation.record(_turn(index, input_tokens=100 * (index + 1), text_chars=400))

    dropped_before = conversation.num_entries_dropped(capabilities)
    usage_before = [entry.usage.input_tokens for entry in conversation.entries]
    images_before = sum(image_count(entry.messages) for entry in conversation.entries)

    conversation.evict_observations(capabilities.preserve_last_frame_for_n_turns)

    assert dropped_before > 0  # a non-trivial decision, so the invariance is worth checking
    assert conversation.num_entries_dropped(capabilities) == dropped_before
    assert [entry.usage.input_tokens for entry in conversation.entries] == usage_before
    assert images_before == 40  # the test is not vacuous: images were present to begin with
    assert sum(image_count(entry.messages) for entry in conversation.entries) == 1  # window kept 1


def test_render_bounds_growth_and_windows_images() -> None:
    """F1/#4: past the window and limit, render caps turns and keeps images only within the window.

    This is the guarantee the old `TokenAccountant` gave: context does not grow without bound, and
    observations survive only inside the frame window.
    """
    capabilities, protocol = _capabilities_and_protocol(limit=5000, window=1, include_manual=False)
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(40):
        conversation.record(_turn(index, input_tokens=100 * (index + 1), text_chars=400))

    rendered = conversation.render(capabilities)

    assert (
        0 < _rendered_turns(rendered) < 20
    )  # truncation bounds growth well below the 40 recorded
    assert image_count(rendered) == 1  # window=1 keeps the last frame only


def test_morse_turn_of_sixteen_frames_collapses_to_one_image_in_render() -> None:
    """A 16-frame turn (morse/simon) is stored whole but renders down to a single windowed image.

    `keep_last` is per-part and all 16 frames sit in one `UserPromptPart`, so an in-window turn
    keeps exactly the last frame regardless of how many it holds. The store keeps all 16 until
    eviction; render never mutates it.
    """
    capabilities, protocol = _capabilities_and_protocol(
        limit=100_000, window=1, include_manual=False
    )
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    conversation.record(_multi_frame_turn(0, frames=16, input_tokens=3400))

    rendered = conversation.render(capabilities)

    assert image_count(conversation.entries[-1].messages) == 16  # stored whole, render is a query
    assert image_count(rendered) == 1  # the one in-window turn collapses 16 frames to its last


def test_eviction_of_a_morse_turn_does_not_shift_truncation() -> None:
    """The window's worst case: a 16-frame turn's recorded size still anchors the calc after evict.

    A morse turn's recorded usage covers all 16 frames it was sent, and that size anchors the calc
    whether or not the bytes still sit in the store. Eviction strips the aged turns' images (never
    the in-window morse turn's), and truncation sizes aged turns by text alone, so the drop count
    and per-turn usage are unchanged — the 16-frame size lingers in the anchor even though the
    rendered turn will carry at most one.
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
    assert images_before == 4 + 16  # four single-frame turns plus the morse turn
    # Eviction strips aged turns whole but leaves the in-window morse turn untouched, so its 16
    # frames stay in the store; only `render` applies the per-part keep_last that collapses them.
    assert sum(image_count(entry.messages) for entry in conversation.entries) == 16
    assert image_count(conversation.render(capabilities)) == 1


def test_long_monotonic_conversation_stays_bounded_and_keeps_pinned() -> None:
    """Three hundred ever-growing turns: the store grows, render stays capped, the manual lives.

    No feedback here — each turn is bigger than the last — so this stresses the drop loop at scale:
    it must never drop the pinned manual, never drop every turn, and hold the rendered prompt far
    below the recorded history.
    """
    capabilities, protocol = _capabilities_and_protocol(limit=5000, window=1, include_manual=True)
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(300):
        conversation.record(_turn(index, input_tokens=100 * (index + 1), text_chars=400))

    rendered = conversation.render(capabilities)

    assert _recorded_turns(conversation) == 300  # the append-only store holds everything
    assert 0 < _rendered_turns(rendered) < 40  # render stays bounded despite 300 recorded turns
    assert conversation.entries[0].pinned  # the manual is never truncated


def test_long_growing_conversation_with_morse_spikes_stays_bounded() -> None:
    """Two hundred growing turns with a 16-frame morse turn every 25: the run stays well-behaved.

    Each turn is larger than the last (accumulating context), with periodic morse spikes standing
    in for blinking-light modules. Across the whole run the store keeps every turn, the render
    stays bounded — a recent stretch of turns is retained, never zero and never all two hundred —
    and per-turn eviction holds observation images to the single windowed frame no matter how many
    a morse turn had. The manual is left out so the image count reflects observations alone.
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
    assert _recorded_turns(conversation) == 200  # the append-only store holds every turn
    assert 0 < max(rendered_turn_counts) < 40  # bounded above; context is retained on normal turns
    assert image_count(rendered) <= 1  # window=1 caps observation images even across morse spikes


def test_a_recent_morse_spike_truncates_far_harder_than_its_size() -> None:
    """One morse turn can shed the whole prior history, because its own frames fill the budget.

    A 16-frame observation is sent in full, so the turn's real recorded size jumps far past the
    budget on its own. Truncation anchors on that size and drops older turns to make room, but each
    older turn frees only its little text once its image has aged out of the window — so it sheds
    every droppable turn and the morse turn still only just fits. A steady run of small turns sits
    under budget and drops nothing; appending the one morse turn sheds most of what came before.
    """
    capabilities, protocol = _capabilities_and_protocol(limit=5000, window=1, include_manual=False)
    conversation = Conversation.begin(capabilities=capabilities, protocol=protocol)
    for index in range(8):
        conversation.record(_turn(index, input_tokens=300))

    dropped_before_spike = conversation.num_entries_dropped(capabilities)
    conversation.record(_multi_frame_turn(8, frames=16, input_tokens=300 + 3200))
    dropped_after_spike = conversation.num_entries_dropped(capabilities)

    assert dropped_before_spike == 0  # eight flat turns under budget need no truncation
    assert dropped_after_spike >= 5  # the single morse turn sheds most of the prior history
