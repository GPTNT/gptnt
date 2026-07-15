import itertools
import math

from gptnt.players.conversation._entry import Entry

_THRESHOLD = 0.9
"""Fraction of `input_tokens_limit` the next prompt can fill before turns are dropped."""

_MIN_TURNS_FOR_FORECAST = 2


def _mean_recent_growth(sizes: list[int], window: int) -> float:
    growths = [later - earlier for earlier, later in itertools.pairwise(sizes)]
    recent = growths[-window:]
    return sum(recent) / len(recent)


def turns_to_drop(
    *, entries: list[Entry], input_tokens_limit: int | None, truncation_forecast_window: int
) -> int:
    """How many of the oldest turns to drop so the next prompt is forecast to fit the budget.

    Forecasts the next prompt as the last measured size plus the mean growth over the last
    `truncation_forecast_window` turns. When that exceeds `input_tokens_limit * _THRESHOLD`, drops
    whole turns, each worth the mean per-turn growth, until it fits. Zero with no limit set, or
    before two turns carry a measured size and there is a growth to forecast from.
    """
    if input_tokens_limit is None:
        return 0

    # Get the sizes of non-pinned entries
    sizes = [entry.total_input_tokens for entry in entries if not entry.pinned]
    # minimum number of turns needed to forecast the next prompt
    if len(sizes) < _MIN_TURNS_FOR_FORECAST:
        return 0

    # Calculate the forecast budget and overshoot
    budget = input_tokens_limit * _THRESHOLD
    forecast = sizes[-1] + max(_mean_recent_growth(sizes, truncation_forecast_window), 0)
    overshoot = forecast - budget
    if overshoot <= 0:
        return 0

    # If the overshoot is positive, calculate the least possible number of turns to drop
    # Get avg number of tokens added per turn
    mean_turn = max(_mean_recent_growth(sizes, len(sizes)), 1)
    # Count how many turns can be dropped
    droppable = sum(1 for entry in entries if not entry.pinned)
    return min(math.ceil(overshoot / mean_turn), droppable)


def truncate(
    *, entries: list[Entry], input_tokens_limit: int | None, truncation_forecast_window: int
) -> list[Entry]:
    """Drop the oldest non-pinned turns the forecast requires to fit the budget.

    Pinned entries are never dropped. With no limit set the entries are returned unchanged.
    """
    count = turns_to_drop(
        entries=entries,
        input_tokens_limit=input_tokens_limit,
        truncation_forecast_window=truncation_forecast_window,
    )
    kept: list[Entry] = []
    dropped = 0
    for entry in entries:
        if not entry.pinned and dropped < count:
            dropped += 1
            continue
        kept.append(entry)
    return kept
