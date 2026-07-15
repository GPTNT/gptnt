import copy
import datetime
from typing import override

import pytest
from pydantic_ai import (
    BinaryContent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RequestUsage,
    TextPart,
    UserPromptPart,
    _utils as pai_utils,
)
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.usage import UsageLimits
from pytest_cases import parametrize, parametrize_with_cases

from gptnt.players.conversation import Conversation
from gptnt.players.conversation._entry import Entry
from gptnt.players.conversation._observations import (
    remove_binary_content_from_messages,
    remove_binary_content_outside_window,
)
from gptnt.players.deps import PlayerDeps
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol

from tests._cases.messages import TEST_TOKENS_PER_IMAGE
from tests._cases.protocol import ProtocolCases

_FIXED_TIMESTAMP = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)


class _FixedDatetime(datetime.datetime):
    @override
    @classmethod
    def now(cls, tz: datetime.tzinfo | None = None) -> datetime.datetime:
        return _FIXED_TIMESTAMP


@pytest.fixture
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pai_utils, "datetime", _FixedDatetime)


def _capabilities(window: int) -> PlayerCapabilities:
    return PlayerCapabilities(
        player_name="test-player",
        player_type="ai",
        structured_output_mode="prompted",
        interaction_location_method="coordinates",
        preserve_last_frame_for_n_turns=window,
        tokens_per_image=TEST_TOKENS_PER_IMAGE,
        usage_limits=UsageLimits(),
    )


def _turn(role: str, observations: int, index: int) -> list[ModelMessage]:
    content: list[object] = [TextPart(content=f"What should I do on turn {index}?")]
    if role == "defuser":
        content += [BinaryContent(data=b"\x89PNG-fake", media_type="image/png")] * observations
    return [
        ModelRequest(parts=[UserPromptPart(content=content, timestamp=_FIXED_TIMESTAMP)]),
        ModelResponse(
            parts=[TextPart(content=f"Response for turn {index}.")],
            usage=RequestUsage(input_tokens=100),
            timestamp=_FIXED_TIMESTAMP,
        ),
    ]


def _dump(messages: list[ModelMessage]) -> bytes:
    return ModelMessagesTypeAdapter.dump_json(messages)


def _image_count(messages: list[ModelMessage]) -> int:
    return sum(
        isinstance(item, BinaryContent)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart) and not isinstance(part.content, str)
        for item in part.content
    )


@pytest.mark.usefixtures("frozen_clock")
@parametrize_with_cases("protocol", cases=ProtocolCases)
@parametrize("window", [0, 1, 3])
@parametrize("observations", [0, 1, 3])
@parametrize("turns", [1, 5])
def test_render_is_pure_and_windows_observations(
    protocol: PlayerProtocol, window: int, observations: int, turns: int
) -> None:
    if protocol.role != "defuser" and observations:
        pytest.skip("only defusers receive observations")

    deps = PlayerDeps(capabilities=_capabilities(window), protocol=protocol)
    conversation = Conversation.begin(deps)
    for index in range(turns):
        conversation.record(copy.deepcopy(_turn(protocol.role, observations, index)))
        conversation.evict_observations(window)
        assert _dump(conversation.render(deps)) == _dump(conversation.render(deps))

    requests = [
        message for message in conversation.render(deps) if isinstance(message, ModelRequest)
    ]
    manual_offset = int(protocol.include_manual)
    for index in range(turns):
        in_window = window > 0 and index >= turns - window
        assert _image_count([requests[index + manual_offset]]) == int(
            in_window and protocol.role == "defuser" and observations > 0
        )


@pytest.mark.usefixtures("frozen_clock")
def test_eviction_preserves_manual_images_and_rendered_history() -> None:
    protocol = PlayerProtocol(
        role="defuser", communication_style="sync", is_playing_alone=False, include_manual=True
    )
    deps = PlayerDeps(capabilities=_capabilities(1), protocol=protocol)
    conversation = Conversation.begin(deps)
    conversation.record(_turn("defuser", 3, 0))
    conversation.record(_turn("defuser", 3, 1))
    rendered_before = _dump(conversation.render(deps))

    conversation.evict_observations(1)

    assert _image_count(conversation.entries[0].messages) > 0
    assert _image_count(conversation.entries[1].messages) == 0
    assert _image_count(conversation.entries[2].messages) == 3
    assert _dump(conversation.render(deps)) == rendered_before


def test_evict_binary_content_keeps_last_per_part() -> None:
    """`_evict_binary_content` with `keep_last` keeps the last image in each user prompt."""
    content: list[object] = [
        TextPart(content="frames"),
        BinaryContent(data=b"a", media_type="image/png"),
        BinaryContent(data=b"b", media_type="image/png"),
    ]
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content=content, timestamp=_FIXED_TIMESTAMP)])
    ]

    assert _image_count(remove_binary_content_from_messages(messages, keep_last=True)) == 1
    assert _image_count(remove_binary_content_from_messages(messages, keep_last=False)) == 0
    assert _image_count(messages) == 2


def test_window_keeps_last_image_only_in_recent_non_pinned_entries() -> None:
    entries = [
        Entry(
            messages=[
                ModelRequest(
                    parts=[
                        UserPromptPart(
                            content=[
                                BinaryContent(data=b"a", media_type="image/png"),
                                BinaryContent(data=b"b", media_type="image/png"),
                            ],
                            timestamp=_FIXED_TIMESTAMP,
                        )
                    ]
                )
            ]
        )
        for _ in range(3)
    ]

    windowed = remove_binary_content_outside_window(entries=entries, window=1)

    assert [_image_count(entry.messages) for entry in windowed] == [0, 0, 1]
    assert [_image_count(entry.messages) for entry in entries] == [2, 2, 2]
