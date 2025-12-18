from hypothesis import given, strategies as st

from gptnt.common.image_ops import ImageDimensions
from gptnt.ktane.manual import NEEDY_MODULE_PAGE_NUMS
from gptnt.prompts.manual import load_manual_as_prompt


@given(
    width=st.integers(min_value=100, max_value=640),
    height=st.integers(min_value=100, max_value=640),
)
def test_manual_loads_consistently_without_error(width: int, height: int) -> None:
    """Test that the manual loads from the function without error."""
    desired_image_dimensions = ImageDimensions(width, height)
    manual_prompt = load_manual_as_prompt(desired_image_dimensions=desired_image_dimensions)
    assert manual_prompt
    manual_prompt = load_manual_as_prompt(desired_image_dimensions=desired_image_dimensions)
    assert manual_prompt
    manual_prompt = load_manual_as_prompt(desired_image_dimensions=desired_image_dimensions)
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


# @st.composite
# def player_deps_strategy(draw: st.DrawFn) -> PlayerDeps:
#     try:
#         protocol = draw(st.builds(PlayerProtocol))
#     except ValidationError:
#         return draw(player_deps_strategy())
#     try:
#         capabilities = draw(st.builds(PlayerCapabilities))
#     except ValidationError:
#         return draw(player_deps_strategy())

#     return PlayerDeps(protocol=protocol, capabilities=capabilities)


# @given(player_deps_strategy())
# def test_prompts_load_for_protocol(deps: PlayerDeps) -> None:
#     instruction = load_instructions(deps)
#     assert instruction


# @given(player_deps_strategy())
# def test_build_output_type_for_protocol_creates_valid_schema(deps: PlayerDeps) -> None:
#     output_type = deps.structured_output_type
#     schema = TypeAdapter(output_type).json_schema()

#     assert output_type
#     assert schema
