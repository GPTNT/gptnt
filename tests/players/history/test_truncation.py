"""Truncation and its size estimate, scenario by scenario.

Truncation answers one question: will the history plus the next observation fit under
`input_tokens_limit`? It anchors on the real measured size of the latest prompt and drops whole
oldest turns until there is room, sizing each dropped turn from a rough per-turn estimate — text
from its length, images at `tokens_per_image`, none once a turn ages out of the window.

The tests below fix each situation that estimate was built for: budgets met and exceeded, images
sized in-window versus aged out, pinned and newest turns kept, the latest prompt standing in for
the next observation, and the cache sub-counts not inflating the anchor.
"""

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
from gptnt.players.conversation._sizing import estimate_rendered_tokens
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
    """A turn whose anchor size is `input_tokens` and whose content is `text_chars` and `images`.

    The images sit in a single user-prompt part, as a real multi-frame observation does, so the
    window keeps one of them and a pinned entry keeps them all.
    """
    prompt: list[object] = ["x" * text_chars]
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


def _drop(entries: list[Entry], **overrides: object) -> int:
    kwargs: dict[str, object] = {
        "input_tokens_limit": 1000,
        "preserve_window": 0,
        "tokens_per_image": 0,
        "max_observations_per_request": 0,
    }
    kwargs.update(overrides)
    return turns_to_drop(entries=entries, **kwargs)


# --- the size estimate ------------------------------------------------------------------------


def test_text_is_sized_at_four_characters_per_token() -> None:
    entry = _turn(input_tokens=0, text_chars=40)

    assert estimate_rendered_tokens(entry, in_window=False, tokens_per_image=100) == 10


def test_in_window_turn_keeps_one_image_per_part() -> None:
    """The window keeps the last image per part, so a five-frame turn counts one image here."""
    entry = _turn(input_tokens=0, text_chars=40, images=5)

    assert estimate_rendered_tokens(entry, in_window=True, tokens_per_image=100) == 10 + 100


def test_aged_turn_is_sized_by_text_alone() -> None:
    """Once a turn ages out of the window its images are stripped, so only its text is left."""
    entry = _turn(input_tokens=0, text_chars=40, images=5)

    assert estimate_rendered_tokens(entry, in_window=False, tokens_per_image=100) == 10


def test_pinned_turn_keeps_every_image() -> None:
    """Pinned entries pass through the window untouched, so all five frames are counted."""
    entry = _turn(input_tokens=0, text_chars=40, images=5, pinned=True)

    assert estimate_rendered_tokens(entry, in_window=True, tokens_per_image=100) == 10 + 5 * 100


def test_zero_tokens_per_image_adds_no_image_size() -> None:
    entry = _turn(input_tokens=0, text_chars=40, images=5)

    assert estimate_rendered_tokens(entry, in_window=True, tokens_per_image=0) == 10


# --- the drop decision ------------------------------------------------------------------------


def test_no_limit_never_truncates() -> None:
    entries = [_turn(input_tokens=10_000, text_chars=400) for _ in range(5)]

    assert _drop(entries, input_tokens_limit=None) == 0


def test_prompt_under_budget_keeps_everything() -> None:
    """The latest prompt sits under 0.9 * limit, so nothing is dropped."""
    entries = [_turn(input_tokens=100, text_chars=400) for _ in range(5)]
    entries.append(_turn(input_tokens=800, text_chars=400))

    assert _drop(entries, input_tokens_limit=1000) == 0


def test_over_budget_drops_oldest_until_it_fits() -> None:
    """Anchor 1200 against a 900 budget overshoots by 300; each aged turn frees 100, so three go.

    Five older turns plus the newest. The newest (the anchor) is never dropped; the oldest three of
    the remaining four are enough to bring 1200 down to 900.
    """
    entries = [_turn(input_tokens=0, text_chars=400) for _ in range(5)]
    entries.append(_turn(input_tokens=1200, text_chars=400))

    assert _drop(entries, input_tokens_limit=1000) == 3


def test_only_the_latest_turn_impacts_the_truncation_decision() -> None:
    """The most recent request usage should be the decider for truncation.

    This is because the most recent one has the most accurate measurement of the prompt size give
    any and all previous truncations.

    Two histories with wildly different old sizes but the same newest size and content drop the
    same number of turns — the anchor is the last real measurement, not a running sum.
    """
    small_olds = [_turn(input_tokens=1, text_chars=400) for _ in range(5)]
    huge_olds = [_turn(input_tokens=9_999, text_chars=400) for _ in range(5)]
    latest = _turn(input_tokens=1200, text_chars=400)

    assert _drop([*small_olds, latest], input_tokens_limit=1000) == _drop(
        [*huge_olds, latest], input_tokens_limit=1000
    )


def test_room_is_reserved_for_the_next_observation() -> None:
    """Space is held back for the worst-case next observation, which lands on top of the render.

    Anchor 850 fits the 900 budget (0.9 * 1000) on its own. Reserving two incoming frames plus one
    of margin at 100 each removes 300 from the budget, so the same history now sheds turns to leave
    room for the frames that will land next. With no image tokens, nothing is reserved and it fits.
    """
    entries = [_turn(input_tokens=0, text_chars=400) for _ in range(5)]
    entries.append(_turn(input_tokens=850, text_chars=400))

    assert _drop(entries, input_tokens_limit=1000) == 0
    assert (
        _drop(
            entries, input_tokens_limit=1000, tokens_per_image=100, max_observations_per_request=2
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
    """Even a single turn far over budget stays: there is nothing older to drop for it."""
    entries = [_turn(input_tokens=10_000, text_chars=400)]

    assert _drop(entries, input_tokens_limit=1000) == 0


def test_a_prompt_larger_than_the_whole_history_drops_all_but_the_newest() -> None:
    """When even shedding every older turn cannot fit, truncation drops all it may and stops."""
    entries = [_turn(input_tokens=0, text_chars=40) for _ in range(4)]
    entries.append(_turn(input_tokens=100_000, text_chars=40))

    assert _drop(entries, input_tokens_limit=1000) == 4


# --- the cache sub-counts (guarding the double-count fix) --------------------------------------


def test_total_input_tokens_excludes_cache_subcounts() -> None:
    """`input_tokens` is the whole prompt; the cache buckets are sub-counts within it.

    genai-prices reports cache reads/writes as sub-counts of `input_tokens`, so summing them
    double-counts — nearly doubling the anchor on cache-heavy providers and truncating for nothing.
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
    """The latest prompt's cache split must not move the drop count: only its total matters."""
    olds = [_turn(input_tokens=0, text_chars=400) for _ in range(5)]
    fresh_latest = _turn(input_tokens=1200, text_chars=400)
    cached_latest = _turn(input_tokens=1200, text_chars=400, cache_read_tokens=1100)

    assert _drop([*olds, fresh_latest], input_tokens_limit=1000) == _drop(
        [*olds, cached_latest], input_tokens_limit=1000
    )
