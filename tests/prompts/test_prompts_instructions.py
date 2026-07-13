from typing import Any

from hypothesis import given, strategies as st
from pydantic import TypeAdapter, ValidationError

from gptnt.ktane.actions import RelativeCoordinate
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
    capabilities = PlayerCapabilities(player_name="test-player", player_type="ai")
    deps = PlayerDeps(capabilities=capabilities, protocol=protocol)

    _ = deps.structured_output_type

    # The generic action alias keeps its bracketed name; the union no longer mutates it.
    assert "[" in InteractGameAction[RelativeCoordinate].__name__
