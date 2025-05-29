import pytest
from pydantic.type_adapter import TypeAdapter
from pytest_cases import parametrize

from gptnt.common.paths import Paths
from gptnt.common.prompt_cache import PromptCache
from gptnt.ktane.manual import NEEDY_MODULE_PAGE_NUMS, KtaneManualPaths
from gptnt.players.prompts import load_instructions_for_spec, load_manual_as_prompt
from gptnt.players.spec import CommunicationStyle, PlayerRole, PlayerSpec


@pytest.fixture(scope="session", autouse=True)
def prompt_cache() -> None:
    """Fixture to set up the prompt cache before running tests."""
    paths = Paths()
    ktane_manual = KtaneManualPaths()
    PromptCache.initialise(paths.prompts, ktane_manual.text_dir, ktane_manual.images_512_dir)


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


@parametrize("role", ["defuser", "expert"])
@parametrize("communication_style", ["async", "sync"])
@parametrize("is_playing_alone", [True, False], ids=["solo", "multiplayer"])
@parametrize("allow_thoughts_in_output", [True, False], ids=["ReAct", "Act"])
@parametrize("include_manual", [True, False], ids=["manual", "no_manual"])
def test_prompts_load_for_spec(
    *,
    role: PlayerRole,
    communication_style: CommunicationStyle,
    is_playing_alone: bool,
    allow_thoughts_in_output: bool,
    include_manual: bool,
) -> None:
    if role == "expert" and is_playing_alone:
        # Expert cannot play alone
        pytest.skip("Expert cannot play alone")

    player_spec = PlayerSpec(
        role=role,
        communication_style=communication_style,
        is_playing_alone=is_playing_alone,
        allow_thoughts_output=allow_thoughts_in_output,
        allow_thoughts_in_history=allow_thoughts_in_output,
        allow_outputs_in_history=True,
        include_manual=include_manual,
        thinking_framework="react" if allow_thoughts_in_output else "act",
    )

    instruction = load_instructions_for_spec(player_spec)
    assert instruction


@parametrize("role", ["defuser", "expert"])
@parametrize("communication_style", ["async", "sync"])
@parametrize("is_playing_alone", [True, False], ids=["solo", "multiplayer"])
@parametrize("allow_thoughts_in_output", [True, False], ids=["ReAct", "Act"])
@parametrize("include_manual", [True, False], ids=["manual", "no_manual"])
def test_build_output_type_for_spec_creates_valid_schema(
    *,
    role: PlayerRole,
    communication_style: CommunicationStyle,
    is_playing_alone: bool,
    allow_thoughts_in_output: bool,
    include_manual: bool,
) -> None:
    if role == "expert" and is_playing_alone:
        # Expert cannot play alone
        pytest.skip("Expert cannot play alone")

    player_spec = PlayerSpec(
        role=role,
        communication_style=communication_style,
        is_playing_alone=is_playing_alone,
        allow_thoughts_output=allow_thoughts_in_output,
        allow_thoughts_in_history=allow_thoughts_in_output,
        allow_outputs_in_history=True,
        include_manual=include_manual,
        thinking_framework="react" if allow_thoughts_in_output else "act",
    )

    output_type = player_spec.output_type
    schema = TypeAdapter(output_type).json_schema()

    assert output_type
    assert schema
