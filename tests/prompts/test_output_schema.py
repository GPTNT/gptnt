import inspect
from typing import TYPE_CHECKING

from inline_snapshot import snapshot

from gptnt.players.deps import PlayerDeps
from gptnt.prompts.output_schema import (
    PROMPTED_OUTPUT_TEMPLATE,
    create_output_schema_for_instructions,
)

from tests._cases.capabilities import CapabilitiesCases
from tests._cases.protocol import ProtocolCases

if TYPE_CHECKING:
    from gptnt.players.specification import PlayerCapabilities, PlayerProtocol


def _case_instances[CaseT](cases: type) -> dict[str, CaseT]:
    """Map each `case_*` method of a pytest-cases class to its returned value, keyed by name."""
    instance = cases()
    return {
        name.removeprefix("case_"): method()
        for name, method in inspect.getmembers(instance, inspect.ismethod)
        if name.startswith("case_")
    }


def _render_for_real_deps() -> dict[str, str]:
    """Render the prompted schema for every real protocol/capability combination the app builds."""
    protocols: dict[str, PlayerProtocol] = _case_instances(ProtocolCases)
    capabilities: dict[str, PlayerCapabilities] = {
        name: capability
        for name, capability in _case_instances(CapabilitiesCases).items()
        if "prompted" in name
    }
    return {
        f"{protocol_name}/{capability_name}": create_output_schema_for_instructions(
            PlayerDeps(protocol=protocol, capabilities=capability).structured_output_type,
            template=PROMPTED_OUTPUT_TEMPLATE,
        )
        for protocol_name, protocol in protocols.items()
        for capability_name, capability in capabilities.items()
    }


# Rendering runs through the private `pydantic_ai._output` builders (see `output_schema`). Pinning
# the exact text they produce over the real `structured_output_type` of every protocol/capability
# combination means a pydantic-ai upgrade that changes those builders fails here, not in a live
# prompt. Regenerate with `pytest --inline-snapshot=create` when the schema is meant to change.
def test_prompted_schema_render_is_pinned() -> None:
    assert _render_for_real_deps() == snapshot(
        {
            "defuser/prompted_absolute_coordinates": """\
Always respond with a JSON object that's compatible with this schema:

    {"type": "object", "properties": {"result": {"anyOf": [{"type": "object", "properties": {"kind": {"type": "string", "const": "do_nothing"}, "data": {"properties": {}, "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "do_nothing", "description": "Create a 'do nothing' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "send_message"}, "data": {"properties": {"message": {"type": "string"}}, "required": ["message"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "send_message", "description": "Create a 'send message' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "interact_game"}, "data": {"properties": {"action": {"$ref": "#/$defs/GameActionType"}, "location": {"anyOf": [{"$ref": "#/$defs/PixelLocation"}, {"type": "null"}], "default": null}}, "required": ["action"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "interact_game"}]}}, "required": ["result"], "additionalProperties": false, "$defs": {"GameActionType": {"description": "Actions that can be performed in the game.", "enum": ["left", "right", "flip", "up", "down", "out", "click", "hold", "release"], "title": "GameActionType", "type": "string"}, "PixelLocation": {"description": "Absolute pixel coordinate to interact with in the game.", "properties": {"x": {"minimum": 0, "type": "integer"}, "y": {"minimum": 0, "type": "integer"}}, "required": ["x", "y"], "title": "PixelLocation", "type": "object"}}}
""",
            "defuser/prompted_normalised_coordinates": """\
Always respond with a JSON object that's compatible with this schema:

    {"type": "object", "properties": {"result": {"anyOf": [{"type": "object", "properties": {"kind": {"type": "string", "const": "do_nothing"}, "data": {"properties": {}, "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "do_nothing", "description": "Create a 'do nothing' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "send_message"}, "data": {"properties": {"message": {"type": "string"}}, "required": ["message"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "send_message", "description": "Create a 'send message' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "interact_game"}, "data": {"properties": {"action": {"$ref": "#/$defs/GameActionType"}, "location": {"anyOf": [{"$ref": "#/$defs/ScaledLocation"}, {"type": "null"}], "default": null}}, "required": ["action"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "interact_game"}]}}, "required": ["result"], "additionalProperties": false, "$defs": {"GameActionType": {"description": "Actions that can be performed in the game.", "enum": ["left", "right", "flip", "up", "down", "out", "click", "hold", "release"], "title": "GameActionType", "type": "string"}, "ScaledLocation": {"description": "Normalised coordinate to interact with in the game, between 0 and 1000.", "properties": {"x": {"minimum": 0, "type": "integer"}, "y": {"minimum": 0, "type": "integer"}}, "required": ["x", "y"], "title": "ScaledLocation", "type": "object"}}}
""",
            "defuser/prompted_set_of_marks": """\
Always respond with a JSON object that's compatible with this schema:

    {"type": "object", "properties": {"result": {"anyOf": [{"type": "object", "properties": {"kind": {"type": "string", "const": "do_nothing"}, "data": {"properties": {}, "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "do_nothing", "description": "Create a 'do nothing' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "send_message"}, "data": {"properties": {"message": {"type": "string"}}, "required": ["message"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "send_message", "description": "Create a 'send message' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "interact_game"}, "data": {"properties": {"action": {"$ref": "#/$defs/GameActionType"}, "location": {"anyOf": [{"$ref": "#/$defs/SingleAlphabetLetter"}, {"type": "null"}], "default": null}}, "required": ["action"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "interact_game"}]}}, "required": ["result"], "additionalProperties": false, "$defs": {"GameActionType": {"description": "Actions that can be performed in the game.", "enum": ["left", "right", "flip", "up", "down", "out", "click", "hold", "release"], "title": "GameActionType", "type": "string"}, "SingleAlphabetLetter": {"maxLength": 1, "type": "string"}}}
""",
            "defuser_with_manual/prompted_absolute_coordinates": """\
Always respond with a JSON object that's compatible with this schema:

    {"type": "object", "properties": {"result": {"anyOf": [{"type": "object", "properties": {"kind": {"type": "string", "const": "do_nothing"}, "data": {"properties": {}, "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "do_nothing", "description": "Create a 'do nothing' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "send_message"}, "data": {"properties": {"message": {"type": "string"}}, "required": ["message"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "send_message", "description": "Create a 'send message' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "interact_game"}, "data": {"properties": {"action": {"$ref": "#/$defs/GameActionType"}, "location": {"anyOf": [{"$ref": "#/$defs/PixelLocation"}, {"type": "null"}], "default": null}}, "required": ["action"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "interact_game"}]}}, "required": ["result"], "additionalProperties": false, "$defs": {"GameActionType": {"description": "Actions that can be performed in the game.", "enum": ["left", "right", "flip", "up", "down", "out", "click", "hold", "release"], "title": "GameActionType", "type": "string"}, "PixelLocation": {"description": "Absolute pixel coordinate to interact with in the game.", "properties": {"x": {"minimum": 0, "type": "integer"}, "y": {"minimum": 0, "type": "integer"}}, "required": ["x", "y"], "title": "PixelLocation", "type": "object"}}}
""",
            "defuser_with_manual/prompted_normalised_coordinates": """\
Always respond with a JSON object that's compatible with this schema:

    {"type": "object", "properties": {"result": {"anyOf": [{"type": "object", "properties": {"kind": {"type": "string", "const": "do_nothing"}, "data": {"properties": {}, "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "do_nothing", "description": "Create a 'do nothing' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "send_message"}, "data": {"properties": {"message": {"type": "string"}}, "required": ["message"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "send_message", "description": "Create a 'send message' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "interact_game"}, "data": {"properties": {"action": {"$ref": "#/$defs/GameActionType"}, "location": {"anyOf": [{"$ref": "#/$defs/ScaledLocation"}, {"type": "null"}], "default": null}}, "required": ["action"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "interact_game"}]}}, "required": ["result"], "additionalProperties": false, "$defs": {"GameActionType": {"description": "Actions that can be performed in the game.", "enum": ["left", "right", "flip", "up", "down", "out", "click", "hold", "release"], "title": "GameActionType", "type": "string"}, "ScaledLocation": {"description": "Normalised coordinate to interact with in the game, between 0 and 1000.", "properties": {"x": {"minimum": 0, "type": "integer"}, "y": {"minimum": 0, "type": "integer"}}, "required": ["x", "y"], "title": "ScaledLocation", "type": "object"}}}
""",
            "defuser_with_manual/prompted_set_of_marks": """\
Always respond with a JSON object that's compatible with this schema:

    {"type": "object", "properties": {"result": {"anyOf": [{"type": "object", "properties": {"kind": {"type": "string", "const": "do_nothing"}, "data": {"properties": {}, "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "do_nothing", "description": "Create a 'do nothing' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "send_message"}, "data": {"properties": {"message": {"type": "string"}}, "required": ["message"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "send_message", "description": "Create a 'send message' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "interact_game"}, "data": {"properties": {"action": {"$ref": "#/$defs/GameActionType"}, "location": {"anyOf": [{"$ref": "#/$defs/SingleAlphabetLetter"}, {"type": "null"}], "default": null}}, "required": ["action"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "interact_game"}]}}, "required": ["result"], "additionalProperties": false, "$defs": {"GameActionType": {"description": "Actions that can be performed in the game.", "enum": ["left", "right", "flip", "up", "down", "out", "click", "hold", "release"], "title": "GameActionType", "type": "string"}, "SingleAlphabetLetter": {"maxLength": 1, "type": "string"}}}
""",
            "expert/prompted_absolute_coordinates": """\
Always respond with a JSON object that's compatible with this schema:

    {"type": "object", "properties": {"result": {"anyOf": [{"type": "object", "properties": {"kind": {"type": "string", "const": "do_nothing"}, "data": {"properties": {}, "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "do_nothing", "description": "Create a 'do nothing' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "send_message"}, "data": {"properties": {"message": {"type": "string"}}, "required": ["message"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "send_message", "description": "Create a 'send message' action."}]}}, "required": ["result"], "additionalProperties": false, "description": "Create a 'send message' action."}
""",
            "expert/prompted_normalised_coordinates": """\
Always respond with a JSON object that's compatible with this schema:

    {"type": "object", "properties": {"result": {"anyOf": [{"type": "object", "properties": {"kind": {"type": "string", "const": "do_nothing"}, "data": {"properties": {}, "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "do_nothing", "description": "Create a 'do nothing' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "send_message"}, "data": {"properties": {"message": {"type": "string"}}, "required": ["message"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "send_message", "description": "Create a 'send message' action."}]}}, "required": ["result"], "additionalProperties": false, "description": "Create a 'send message' action."}
""",
            "expert/prompted_set_of_marks": """\
Always respond with a JSON object that's compatible with this schema:

    {"type": "object", "properties": {"result": {"anyOf": [{"type": "object", "properties": {"kind": {"type": "string", "const": "do_nothing"}, "data": {"properties": {}, "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "do_nothing", "description": "Create a 'do nothing' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "send_message"}, "data": {"properties": {"message": {"type": "string"}}, "required": ["message"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "send_message", "description": "Create a 'send message' action."}]}}, "required": ["result"], "additionalProperties": false, "description": "Create a 'send message' action."}
""",
            "solo_defuser/prompted_absolute_coordinates": """\
Always respond with a JSON object that's compatible with this schema:

    {"type": "object", "properties": {"result": {"anyOf": [{"type": "object", "properties": {"kind": {"type": "string", "const": "do_nothing"}, "data": {"properties": {}, "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "do_nothing", "description": "Create a 'do nothing' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "interact_game"}, "data": {"properties": {"action": {"$ref": "#/$defs/GameActionType"}, "location": {"anyOf": [{"$ref": "#/$defs/PixelLocation"}, {"type": "null"}], "default": null}}, "required": ["action"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "interact_game"}]}}, "required": ["result"], "additionalProperties": false, "$defs": {"GameActionType": {"description": "Actions that can be performed in the game.", "enum": ["left", "right", "flip", "up", "down", "out", "click", "hold", "release"], "title": "GameActionType", "type": "string"}, "PixelLocation": {"description": "Absolute pixel coordinate to interact with in the game.", "properties": {"x": {"minimum": 0, "type": "integer"}, "y": {"minimum": 0, "type": "integer"}}, "required": ["x", "y"], "title": "PixelLocation", "type": "object"}}}
""",
            "solo_defuser/prompted_normalised_coordinates": """\
Always respond with a JSON object that's compatible with this schema:

    {"type": "object", "properties": {"result": {"anyOf": [{"type": "object", "properties": {"kind": {"type": "string", "const": "do_nothing"}, "data": {"properties": {}, "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "do_nothing", "description": "Create a 'do nothing' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "interact_game"}, "data": {"properties": {"action": {"$ref": "#/$defs/GameActionType"}, "location": {"anyOf": [{"$ref": "#/$defs/ScaledLocation"}, {"type": "null"}], "default": null}}, "required": ["action"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "interact_game"}]}}, "required": ["result"], "additionalProperties": false, "$defs": {"GameActionType": {"description": "Actions that can be performed in the game.", "enum": ["left", "right", "flip", "up", "down", "out", "click", "hold", "release"], "title": "GameActionType", "type": "string"}, "ScaledLocation": {"description": "Normalised coordinate to interact with in the game, between 0 and 1000.", "properties": {"x": {"minimum": 0, "type": "integer"}, "y": {"minimum": 0, "type": "integer"}}, "required": ["x", "y"], "title": "ScaledLocation", "type": "object"}}}
""",
            "solo_defuser/prompted_set_of_marks": """\
Always respond with a JSON object that's compatible with this schema:

    {"type": "object", "properties": {"result": {"anyOf": [{"type": "object", "properties": {"kind": {"type": "string", "const": "do_nothing"}, "data": {"properties": {}, "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "do_nothing", "description": "Create a 'do nothing' action."}, {"type": "object", "properties": {"kind": {"type": "string", "const": "interact_game"}, "data": {"properties": {"action": {"$ref": "#/$defs/GameActionType"}, "location": {"anyOf": [{"$ref": "#/$defs/SingleAlphabetLetter"}, {"type": "null"}], "default": null}}, "required": ["action"], "type": "object"}}, "required": ["kind", "data"], "additionalProperties": false, "title": "interact_game"}]}}, "required": ["result"], "additionalProperties": false, "$defs": {"GameActionType": {"description": "Actions that can be performed in the game.", "enum": ["left", "right", "flip", "up", "down", "out", "click", "hold", "release"], "title": "GameActionType", "type": "string"}, "SingleAlphabetLetter": {"maxLength": 1, "type": "string"}}}
""",
        }
    )
