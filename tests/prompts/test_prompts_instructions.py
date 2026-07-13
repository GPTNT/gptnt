from typing import Any

from hypothesis import given, strategies as st
from pydantic import TypeAdapter, ValidationError

from gptnt.players.actions import InteractGameAction
from gptnt.players.deps import PlayerDeps
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol
from gptnt.prompts.instructions import load_instructions


def _iter_titles(schema: dict[str, Any]) -> list[str]:
    titles = [schema["title"]] if "title" in schema else []
    titles.extend(sub["title"] for sub in schema.get("$defs", {}).values() if "title" in sub)
    return titles


@st.composite
def player_deps_strategy(draw: st.DrawFn) -> PlayerDeps:
    try:
        protocol = draw(st.builds(PlayerProtocol))
    except ValidationError:
        return draw(player_deps_strategy())
    try:
        capabilities = draw(st.builds(PlayerCapabilities))
    except ValidationError:
        return draw(player_deps_strategy())

    return PlayerDeps(protocol=protocol, capabilities=capabilities)


@given(player_deps_strategy())
def test_prompts_load_for_protocol(deps: PlayerDeps) -> None:
    instruction = load_instructions(deps.protocol, deps.capabilities)
    assert instruction


@given(player_deps_strategy())
def test_build_output_type_for_protocol_creates_valid_schema(deps: PlayerDeps) -> None:
    output_type = deps.structured_output_type
    schema = TypeAdapter(output_type).json_schema()

    assert output_type
    assert schema

    # Schema titles must stay bracket-free (they feed native/tool/prompted tool naming).
    assert all("[" not in title and "]" not in title for title in _iter_titles(schema))


def test_structured_output_type_does_not_mutate_action_class_names() -> None:
    protocol = PlayerProtocol(
        role="defuser", communication_style="sync", is_playing_alone=False, include_manual=False
    )
    capabilities = PlayerCapabilities(
        player_name="test-player",
        player_type="ai",
        interaction_location_method="coordinates",
        coordinate_mode="absolute",
    )
    deps = PlayerDeps(capabilities=capabilities, protocol=protocol)

    # The exact specialization the union is built from, per the capabilities under test.
    location_type = deps.capabilities.interact_location_type
    specialized = InteractGameAction[location_type]
    assert "[" in specialized.__name__
    assert "]" in specialized.__name__

    _ = deps.structured_output_type

    # Building the union must not mutate the shared, cached specialization's dunders.
    assert InteractGameAction[location_type] is specialized
    assert "[" in specialized.__name__
    assert "]" in specialized.__name__
    assert "[" in specialized.__qualname__
    assert "]" in specialized.__qualname__

    # Its schema title stays bracket-free (it feeds native/tool/prompted tool naming).
    assert all(
        "[" not in title and "]" not in title
        for title in _iter_titles(TypeAdapter(specialized).json_schema())
    )
