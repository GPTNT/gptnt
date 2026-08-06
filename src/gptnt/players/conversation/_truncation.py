from gptnt.players.conversation._entry import Entry
from gptnt.players.conversation._observations import partition_non_pinned_by_window

_THRESHOLD = 0.8
"""Fraction of the input-token limit available to conversation history.

The remaining 20% covers response text added after the previous request and errors in the size
estimates used to remove old turns. Tokens for the next observation are reserved separately.
"""


def turns_to_drop(
    *,
    entries: list[Entry],
    input_tokens_limit: int | None,
    preserve_window: int,
    tokens_per_image: int,
    max_observations_per_request: int,
    omitted_count: int = 0,
) -> int:
    """Return how many oldest non-pinned turns the next request must omit.

    `omitted_count` is the number of turns already excluded from every request. The latest provider
    input-token count measures the previous request, which excluded those turns. If it exceeds the
    available budget, this function subtracts the estimated size of additional old turns until the
    prompt fits. It always keeps pinned entries and the newest turn.

    The available budget reserves enough tokens for the maximum next observation plus one extra
    image. A provider count of zero is not a usable measurement, so `omitted_count` remains
    unchanged.
    """
    if input_tokens_limit is None:
        return omitted_count

    non_pinned = [(index, entry) for index, entry in enumerate(entries) if not entry.pinned]
    active = non_pinned[omitted_count:]
    if not active:
        return omitted_count

    reservation = (max_observations_per_request + 1) * tokens_per_image
    budget = input_tokens_limit * _THRESHOLD - reservation
    measured_tokens = active[-1][1].total_input_tokens
    if measured_tokens <= 0 or measured_tokens <= budget:
        return omitted_count

    _, in_window = partition_non_pinned_by_window(entries, window=preserve_window)
    freed = 0
    for dropped, (index, entry) in enumerate(active[:-1], start=1):
        freed += entry.estimated_render_tokens(
            in_window=index in in_window, tokens_per_image=tokens_per_image
        )
        if measured_tokens - freed <= budget:
            return omitted_count + dropped
    return omitted_count + len(active) - 1


def drop_oldest_non_pinned(*, entries: list[Entry], count: int) -> list[Entry]:
    """Omit the first `count` non-pinned entries."""
    kept: list[Entry] = []
    dropped = 0
    for entry in entries:
        if not entry.pinned and dropped < count:
            dropped += 1
            continue
        kept.append(entry)
    return kept


def truncate(
    *,
    entries: list[Entry],
    input_tokens_limit: int | None,
    preserve_window: int,
    tokens_per_image: int,
    max_observations_per_request: int,
) -> list[Entry]:
    """Drop the oldest non-pinned turns needed to fit the budget.

    With no limit set the entries are returned unchanged.
    """
    count = turns_to_drop(
        entries=entries,
        input_tokens_limit=input_tokens_limit,
        preserve_window=preserve_window,
        tokens_per_image=tokens_per_image,
        max_observations_per_request=max_observations_per_request,
    )
    return drop_oldest_non_pinned(entries=entries, count=count)
