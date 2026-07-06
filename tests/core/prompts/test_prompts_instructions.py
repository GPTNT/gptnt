from hypothesis import given, strategies as st
from pydantic import TypeAdapter, ValidationError

from gptnt.players.deps import PlayerDeps
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol
from gptnt.prompts.instructions import load_instructions


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
