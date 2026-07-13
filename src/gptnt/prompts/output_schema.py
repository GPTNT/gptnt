from textwrap import dedent

# pydantic-ai renders the prompted-output JSON schema only onto the parameters it hands a model at
# request time, and its one public route to that text runs a whole agent. These instructions are
# built inside a synchronous callback that already runs within `agent.run`'s event loop, where a
# nested `run_sync` raises "This event loop is already running", so we call the two internal
# builders directly. `tests/prompts/test_output_schema.py` pins the rendered text so a pydantic-ai
# upgrade that moves or changes these internals fails in CI instead of silently in a prompt.
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
    """
    output_schema = OutputSchema[OutputT].build(PromptedOutput(structured_output_type))
    assert output_schema.object_def is not None

    return PromptedOutputSchema.build_instructions(template, output_schema.object_def)
