from textwrap import dedent

from pydantic_ai import PromptedOutput
from pydantic_ai._output import OutputSchema, PromptedOutputSchema

PROMPTED_OUTPUT_TEMPLATE = dedent(
    """Always respond with a JSON object that's compatible with this schema:

    {schema}
    """
)


def create_output_schema_for_instructions[OutputT](
    structured_output_type: type[OutputT], *, template: str
) -> str:
    """Render the prompted-output schema for `structured_output_type` into the given template.

    Reproduces the schema text pydantic-ai injects in `prompted` mode, for models that instead
    return a raw string re-parsed downstream.

    Pydantic AI put the JSON schema for the prompted-output into the parameters when it is called
    by the model at request time, and there is only one public route to that. So we call the
    internal builders for this directly so that we can get the schema text without running a model.
    We use inline-snapshot in the tests to check that the schema has the result of this function
    has not changed unexpectedly, and we can see what happens and update the snapshot accordingly.
    """
    output_schema = OutputSchema[OutputT].build(PromptedOutput(structured_output_type))
    assert output_schema.object_def is not None

    return PromptedOutputSchema.build_instructions(template, output_schema.object_def)
