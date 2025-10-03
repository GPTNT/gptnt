from contextlib import suppress

from hypothesis import given, strategies as st
from pydantic import TypeAdapter, ValidationError

from gptnt.ktane.manual import NEEDY_MODULE_PAGE_NUMS
from gptnt.players.prompts.instructions import load_instructions
from gptnt.players.prompts.manual import load_manual_as_prompt
from gptnt.players.specification import PlayerProtocol


def test_manual_loads_consistently_without_error() -> None:
    """Test that the manual loads from the function without error."""
    manual_prompt = load_manual_as_prompt()
    assert manual_prompt
    manual_prompt = load_manual_as_prompt()
    assert manual_prompt
    manual_prompt = load_manual_as_prompt()
    assert manual_prompt


def test_needy_module_pages_are_skipped() -> None:
    """Test that the needy module pages are skipped."""
    manual_prompt = load_manual_as_prompt()
    mamual_prompt_texts = [page for page in manual_prompt if isinstance(page, str)]

    page_numbers = [
        *[f"{num}/23" for num in NEEDY_MODULE_PAGE_NUMS],
        *[f"Page {num} of 23" for num in NEEDY_MODULE_PAGE_NUMS],
    ]

    for page in mamual_prompt_texts:
        for page_number in page_numbers:
            assert page_number not in page


@st.composite
def player_protocol_strategy(draw: st.DrawFn) -> PlayerProtocol:
    with suppress(ValidationError):
        return draw(st.builds(PlayerProtocol))
    # If the PlayerProtocol is invalid, we can just skip this case
    return draw(player_protocol_strategy())


@given(player_protocol_strategy())
def test_prompts_load_for_protocol(player_protocol: PlayerProtocol) -> None:
    instruction = load_instructions(player_protocol)
    assert instruction


@given(player_protocol_strategy())
def test_build_output_type_for_protocol_creates_valid_schema(
    player_protocol: PlayerProtocol,
) -> None:
    output_type = player_protocol.output_type
    schema = TypeAdapter(output_type).json_schema()

    assert output_type
    assert schema
