from typing import Union

from pydantic import BaseModel

from gptnt.prompts.output_schema import (
    PROMPTED_OUTPUT_TEMPLATE,
    create_output_schema_for_instructions,
)


class Move(BaseModel):
    kind: str
    steps: int


class Wait(BaseModel):
    kind: str


# Rendering depends on the private `pydantic_ai._output` builders (see `output_schema`). This pins
# the exact text they produce so a pydantic-ai upgrade that changes them fails here, not in a live
# prompt. Update the expected string deliberately when the rendered schema is meant to change.
EXPECTED = (
    "Always respond with a JSON object that's compatible with this schema:\n\n"
    '    {"type": "object", "properties": {"result": {"anyOf": ['
    '{"type": "object", "properties": {"kind": {"type": "string", "const": "Move"}, '
    '"data": {"properties": {"kind": {"type": "string"}, "steps": {"type": "integer"}}, '
    '"required": ["kind", "steps"], "type": "object"}}, '
    '"required": ["kind", "data"], "additionalProperties": false, "title": "Move"}, '
    '{"type": "object", "properties": {"kind": {"type": "string", "const": "Wait"}, '
    '"data": {"properties": {"kind": {"type": "string"}}, '
    '"required": ["kind"], "type": "object"}}, '
    '"required": ["kind", "data"], "additionalProperties": false, "title": "Wait"}]}}, '
    '"required": ["result"], "additionalProperties": false}\n'
)


def test_prompted_schema_render_is_pinned() -> None:
    rendered = create_output_schema_for_instructions(
        Union[Move, Wait],  # noqa: UP007
        template=PROMPTED_OUTPUT_TEMPLATE,
    )
    assert rendered == EXPECTED
