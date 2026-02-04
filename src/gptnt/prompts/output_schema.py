from textwrap import dedent

from pydantic_ai import PromptedOutput
from pydantic_ai._output import OutputSchema, PromptedOutputSchema

PROMPTED_OUTPUT_TEMPLATE = dedent(
    """
    Always respond with a JSON object that's compatible with this schema:

    {schema}

    """
)


def create_output_schema_for_instructions[OutputT](
    structured_output_type: type[OutputT], *, template: str
) -> str:
    """Manually create the schema for PromptedOutput based on the current deps."""
    output_schema = OutputSchema[OutputT].build(PromptedOutput(structured_output_type))
    assert output_schema.object_def is not None

    instruction_suffix = PromptedOutputSchema.build_instructions(
        template, output_schema.object_def
    )
    return instruction_suffix
