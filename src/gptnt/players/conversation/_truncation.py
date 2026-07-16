from gptnt.players.conversation._entry import Entry
from gptnt.players.conversation._observations import partition_non_pinned_by_window
from gptnt.players.conversation._sizing import estimate_rendered_tokens

_THRESHOLD = 0.9
"""Fraction of `input_tokens_limit` left for the render after reserving the next observation.

The remaining tenth is slack for the parts the anchor cannot see yet: this turn's response text as
it enters the history, and estimation error in the per-turn sizes.
"""


def turns_to_drop(
    *,
    entries: list[Entry],
    input_tokens_limit: int | None,
    preserve_window: int,
    tokens_per_image: int,
    max_observations_per_request: int,
) -> int:
    """How many oldest turns to drop so the render plus the next observation fits the budget.

    The next observation is sent on top of the render, not inside it: a multi-frame module sends up
    to `max_observations_per_request` frames, so that much space (plus one frame of margin) is held
    back from the budget unconditionally — enough room to land the worst-case incoming frames even
    when the last turn carried none. The decision then anchors on the real measured size of the
    latest prompt — ground truth from the provider, so estimation error re-syncs every turn — and
    when it exceeds the reserved budget, drops whole oldest non-pinned turns until it fits,
    subtracting each dropped turn's estimated rendered size (text from length, images at
    `tokens_per_image`, none once a turn ages out of the window). Pinned entries and the newest
    turn are never dropped. Zero when no limit is set or the latest prompt already fits.
    """
    if input_tokens_limit is None:
        return 0

    non_pinned = [(index, entry) for index, entry in enumerate(entries) if not entry.pinned]
    if not non_pinned:
        return 0

    reservation = (max_observations_per_request + 1) * tokens_per_image
    budget = input_tokens_limit * _THRESHOLD - reservation
    anchor = non_pinned[-1][1].total_input_tokens
    if anchor <= budget:
        return 0

    _, in_window = partition_non_pinned_by_window(entries, window=preserve_window)
    freed = 0
    for dropped, (index, entry) in enumerate(non_pinned[:-1], start=1):
        freed += estimate_rendered_tokens(
            entry, in_window=index in in_window, tokens_per_image=tokens_per_image
        )
        if anchor - freed <= budget:
            return dropped
    return len(non_pinned) - 1


def truncate(
    *,
    entries: list[Entry],
    input_tokens_limit: int | None,
    preserve_window: int,
    tokens_per_image: int,
    max_observations_per_request: int,
) -> list[Entry]:
    """Drop the oldest non-pinned turns needed to fit the budget, keeping pinned entries.

    With no limit set the entries are returned unchanged.
    """
    count = turns_to_drop(
        entries=entries,
        input_tokens_limit=input_tokens_limit,
        preserve_window=preserve_window,
        tokens_per_image=tokens_per_image,
        max_observations_per_request=max_observations_per_request,
    )
    kept: list[Entry] = []
    dropped = 0
    for entry in entries:
        if not entry.pinned and dropped < count:
            dropped += 1
            continue
        kept.append(entry)
    return kept
