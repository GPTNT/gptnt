import datetime

from pydantic_ai import (
    BinaryContent,
    ModelRequest,
    ModelResponse,
    RequestUsage,
    TextPart,
    UserPromptPart,
)

from gptnt.players.conversation._entry import Entry
from gptnt.players.conversation._truncation import truncate, turns_to_drop

_FIXED_TIMESTAMP = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)


def _turn(
    *,
    input_tokens: int,
    text_chars: int = 0,
    images: int = 0,
    cache_read_tokens: int = 0,
    pinned: bool = False,
) -> Entry:
    """Build an entry with measured usage and controllable estimated content.

    All images share one user-prompt part. An in-window entry therefore retains one image, while a
    pinned entry retains every image.
    """
    prompt: list[str | BinaryContent] = ["x" * text_chars]
    prompt.extend(
        BinaryContent(data=b"\x89PNG-fake", media_type="image/png") for _ in range(images)
    )
    return Entry.from_turn(
        messages=[
            ModelRequest(parts=[UserPromptPart(content=prompt, timestamp=_FIXED_TIMESTAMP)]),
            ModelResponse(
                parts=[TextPart(content="")],
                usage=RequestUsage(input_tokens=input_tokens, cache_read_tokens=cache_read_tokens),
                timestamp=_FIXED_TIMESTAMP,
            ),
        ],
        pinned=pinned,
    )


def _drop(entries: list[Entry], **overrides: int | None) -> int:
    kwargs: dict[str, int | None] = {
        "input_tokens_limit": 1000,
        "preserve_window": 0,
        "tokens_per_image": 0,
        "max_observations_per_request": 0,
    }
    kwargs.update(overrides)
    return turns_to_drop(entries=entries, **kwargs)


# The size estimate


def test_text_is_sized_at_four_characters_per_token() -> None:
    entry = _turn(input_tokens=0, text_chars=40)

    assert entry.estimated_render_tokens(in_window=False, tokens_per_image=100) == 10


def test_in_window_turn_keeps_one_image_per_part() -> None:
    """An in-window prompt part contributes one image to the estimate."""
    entry = _turn(input_tokens=0, text_chars=40, images=5)

    assert entry.estimated_render_tokens(in_window=True, tokens_per_image=100) == 10 + 100


def test_aged_turn_is_sized_by_text_alone() -> None:
    """An entry outside the image window contributes only text."""
    entry = _turn(input_tokens=0, text_chars=40, images=5)

    assert entry.estimated_render_tokens(in_window=False, tokens_per_image=100) == 10


def test_pinned_turn_keeps_every_image() -> None:
    """A pinned entry contributes all of its images."""
    entry = _turn(input_tokens=0, text_chars=40, images=5, pinned=True)

    assert entry.estimated_render_tokens(in_window=True, tokens_per_image=100) == 10 + 5 * 100


def test_zero_tokens_per_image_adds_no_image_size() -> None:
    entry = _turn(input_tokens=0, text_chars=40, images=5)

    assert entry.estimated_render_tokens(in_window=True, tokens_per_image=0) == 10


# The drop decision


def test_no_limit_never_truncates() -> None:
    entries = [_turn(input_tokens=10_000, text_chars=400) for _ in range(5)]

    assert _drop(entries, input_tokens_limit=None) == 0


def test_prompt_under_budget_keeps_everything() -> None:
    """A prompt at the 80% threshold does not require truncation."""
    entries = [_turn(input_tokens=100, text_chars=400) for _ in range(5)]
    entries.append(_turn(input_tokens=800, text_chars=400))

    assert _drop(entries, input_tokens_limit=1000) == 0


def test_over_budget_drops_oldest_until_it_fits() -> None:
    """Four 100-token turns reduce a 1,200-token prompt to the 800-token
    budget."""
    entries = [_turn(input_tokens=0, text_chars=400) for _ in range(5)]
    entries.append(_turn(input_tokens=1200, text_chars=400))

    assert _drop(entries, input_tokens_limit=1000) == 4


def test_only_the_latest_turn_impacts_the_truncation_decision() -> None:
    """Only the latest provider measurement determines the starting prompt
    size."""
    small_olds = [_turn(input_tokens=1, text_chars=400) for _ in range(5)]
    huge_olds = [_turn(input_tokens=9_999, text_chars=400) for _ in range(5)]
    latest = _turn(input_tokens=1200, text_chars=400)

    assert _drop([*small_olds, latest], input_tokens_limit=1000) == _drop(
        [*huge_olds, latest], input_tokens_limit=1000
    )


def test_room_is_reserved_for_the_next_observation() -> None:
    """The budget reserves tokens for the largest allowed next observation.

    A 750-token prompt fits within 80% of a 1,000-token limit. Reserving 300 tokens for three
    images reduces the available history budget to 500, which requires truncation.
    """
    entries = [_turn(input_tokens=0, text_chars=400) for _ in range(5)]
    entries.append(_turn(input_tokens=750, text_chars=400))

    assert _drop(entries, input_tokens_limit=1000) == 0
    assert (
        _drop(
            entries, input_tokens_limit=1000, tokens_per_image=100, max_observations_per_request=2
        )
        > 0
    )


def test_room_is_reserved_for_a_sixteen_frame_observation() -> None:
    """A 16-frame limit reserves tokens for 17 calibrated images."""
    entries = [_turn(input_tokens=0, text_chars=400) for _ in range(5)]
    entries.append(_turn(input_tokens=700, text_chars=400))

    assert _drop(entries, input_tokens_limit=5000) == 0
    assert (
        _drop(
            entries, input_tokens_limit=5000, tokens_per_image=200, max_observations_per_request=16
        )
        > 0
    )


def test_pinned_entries_are_never_dropped() -> None:
    pinned = _turn(input_tokens=0, text_chars=400, pinned=True)
    entries = [
        pinned,
        *(_turn(input_tokens=0, text_chars=400) for _ in range(4)),
        _turn(input_tokens=1200, text_chars=400),
    ]

    kept = truncate(
        entries=entries,
        input_tokens_limit=1000,
        preserve_window=0,
        tokens_per_image=0,
        max_observations_per_request=0,
    )

    assert kept[0] is pinned
    assert len(kept) < len(entries)


def test_the_newest_turn_is_never_dropped() -> None:
    """Even one turn far over budget stays because no older turn can be dropped."""
    entries = [_turn(input_tokens=10_000, text_chars=400)]

    assert _drop(entries, input_tokens_limit=1000) == 0


def test_a_prompt_larger_than_the_whole_history_drops_all_but_the_newest() -> None:
    """Truncation keeps the newest turn even when omitting every older turn is
    insufficient."""
    entries = [_turn(input_tokens=0, text_chars=40) for _ in range(4)]
    entries.append(_turn(input_tokens=100_000, text_chars=40))

    assert _drop(entries, input_tokens_limit=1000) == 4


# The cache sub-counts (guarding the double-count fix)


def test_total_input_tokens_excludes_cache_subcounts() -> None:
    """Cache token fields are subsets of `input_tokens`, not additional tokens.

    Adding cache reads and writes to `input_tokens` would count them twice and truncate too early.
    """
    entry = Entry(
        messages=[],
        usage=RequestUsage(
            input_tokens=1000,
            cache_read_tokens=800,
            cache_write_tokens=50,
            cache_audio_read_tokens=20,
        ),
    )

    assert entry.total_input_tokens == 1000


def test_cache_heavy_history_drops_the_same_as_a_fresh_one() -> None:
    """The cache-token split does not affect truncation."""
    olds = [_turn(input_tokens=0, text_chars=400) for _ in range(5)]
    fresh_latest = _turn(input_tokens=1200, text_chars=400)
    cached_latest = _turn(input_tokens=1200, text_chars=400, cache_read_tokens=1100)

    assert _drop([*olds, fresh_latest], input_tokens_limit=1000) == _drop(
        [*olds, cached_latest], input_tokens_limit=1000
    )
