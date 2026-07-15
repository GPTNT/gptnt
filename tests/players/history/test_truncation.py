import datetime

from pydantic_ai import ModelRequest, ModelResponse, RequestUsage, TextPart, UserPromptPart

from gptnt.players.conversation._entry import Entry
from gptnt.players.conversation._truncation import truncate, turns_to_drop
from gptnt.players.specification import PlayerCapabilities

_FIXED_TIMESTAMP = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)


def _entry(index: int, *, input_tokens: int, pinned: bool = False) -> Entry:
    return Entry.from_turn(
        messages=[
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content=f"What should I do on turn {index}?", timestamp=_FIXED_TIMESTAMP
                    )
                ]
            ),
            ModelResponse(
                parts=[TextPart(content=f"Response for turn {index}.")],
                usage=RequestUsage(input_tokens=input_tokens),
                timestamp=_FIXED_TIMESTAMP,
            ),
        ],
        pinned=pinned,
    )


def test_forecast_drops_oldest_non_pinned_turns() -> None:
    entries = [_entry(index, input_tokens=100 * (index + 1)) for index in range(20)]

    count = turns_to_drop(entries=entries, input_tokens_limit=1000, truncation_forecast_window=5)

    assert 0 < count < len(entries)


def test_forecast_requires_two_measured_turns() -> None:
    entries = [_entry(0, input_tokens=10_000)]

    assert turns_to_drop(entries=entries, input_tokens_limit=1, truncation_forecast_window=5) == 0


def test_truncation_keeps_pinned_entries() -> None:
    entries = [_entry(-1, input_tokens=0, pinned=True)] + [
        _entry(index, input_tokens=100 * (index + 1)) for index in range(20)
    ]
    capabilities = PlayerCapabilities(
        player_name="test-player",
        player_type="ai",
        structured_output_mode="prompted",
        interaction_location_method="coordinates",
    )
    capabilities.usage_limits.input_tokens_limit = 1000

    kept = truncate(
        entries=entries,
        input_tokens_limit=capabilities.usage_limits.input_tokens_limit,
        truncation_forecast_window=capabilities.truncation_forecast_window,
    )

    assert kept[0].pinned
    assert len(kept) < len(entries)
